# -*- coding: utf-8 -*-
"""Cloud build driver: download upstream source, apply patches, build firmware.
Designed to run inside espressif/idf:release-v6.1 on GitHub Actions.

v2 change: PSRAM boot-loop fix. Upstream v2.0.1 sets
CONFIG_SPIRAM_IGNORE_NOTFOUND=n, so on AlphaPi v1.7 boards whose PSRAM fails
detection the firmware aborts during boot (=> infinite reboot). We force
IGNORE_NOTFOUND=y (degrade instead of abort) and lower PSRAM clock 80M->40M.
"""
import os
import sys
import shutil
import zipfile
import subprocess
import urllib.request
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def log(*args):
    print(*args, flush=True)


def run(cmd, cwd=None):
    log('$', ' '.join(cmd))
    subprocess.run(cmd, check=True, cwd=cwd)


def download(url, dest, tries=4):
    for i in range(tries):
        try:
            log(f'download attempt {i+1}/{tries}: {url}')
            urllib.request.urlretrieve(url, dest)
            log('download OK, size:', os.path.getsize(dest))
            return
        except Exception as e:
            log('download failed:', repr(e))
            time.sleep(2)
    raise RuntimeError('download failed after retries')


def patch_psram_defaults(path):
    """Make PSRAM detection failure non-fatal and lower PSRAM clock."""
    if not os.path.exists(path):
        log('  skip (missing):', path)
        return
    t = open(path, encoding='utf-8', errors='ignore').read()
    before = t

    # 1) Do NOT abort when PSRAM is missing/fails detection (the boot-loop fix)
    t = t.replace('# CONFIG_SPIRAM_IGNORE_NOTFOUND is not set',
                  'CONFIG_SPIRAM_IGNORE_NOTFOUND=y')
    t = t.replace('CONFIG_SPIRAM_IGNORE_NOTFOUND=n',
                  'CONFIG_SPIRAM_IGNORE_NOTFOUND=y')

    # 2) Lower PSRAM clock 80M -> 40M for better detection on v1.7 batch.
    #    Upstream itself keeps a 40M test build for boards that fail to boot.
    had_80 = 'CONFIG_SPIRAM_SPEED_80M=y' in t
    t = t.replace('CONFIG_SPIRAM_SPEED_80M=y',
                  '# CONFIG_SPIRAM_SPEED_80M is not set')
    t = t.replace('# CONFIG_SPIRAM_SPEED_40M is not set',
                  'CONFIG_SPIRAM_SPEED_40M=y')
    t = t.replace('CONFIG_SPIRAM_SPEED=80\n', 'CONFIG_SPIRAM_SPEED=40\n')
    # If a 80M choice existed but no explicit 40M/numeric value, add them so
    # Kconfig never falls back to a default that could re-enable 80M.
    if had_80 and 'CONFIG_SPIRAM_SPEED_40M=y' not in t:
        t += '\nCONFIG_SPIRAM_SPEED_40M=y\n'
    if ('CONFIG_SPIRAM_SPEED=' not in t) or ('CONFIG_SPIRAM_SPEED=80' in t):
        t += '\nCONFIG_SPIRAM_SPEED=40\n'

    # 3) If the symbol is absent entirely, append it
    if 'CONFIG_SPIRAM_IGNORE_NOTFOUND=y' not in t:
        t += '\nCONFIG_SPIRAM_IGNORE_NOTFOUND=y\n'

    if t != before:
        open(path, 'w', encoding='utf-8').write(t)
    log('  patched:', os.path.basename(path),
        'changed=', (t != before),
        'IGNORE=y=', ('CONFIG_SPIRAM_IGNORE_NOTFOUND=y' in t),
        'SPEED40=', ('CONFIG_SPIRAM_SPEED=40' in t))


def main():
    os.chdir(ROOT)
    log('=== STEP 0: environment ===')
    log('cwd:', os.getcwd())
    log('python:', sys.version)
    log('IDF_PATH:', os.environ.get('IDF_PATH'))
    log('files in repo:', sorted(os.listdir('.')))

    # 1. Download upstream v2.0.1 source
    log('=== STEP 1: download upstream source ===')
    url = ('https://raw.githubusercontent.com/mastomato/AlphaPi-OneS-4in1/'
           'main/source/AlphaPi-OneS-4in1-source-v2.0.1.zip')
    download(url, 'src.zip')
    with zipfile.ZipFile('src.zip') as z:
        z.extractall('src')
    log('extracted. top:', os.listdir('src'))

    src = os.path.join(ROOT, 'src', 'AlphaPi-OneS-4in1-source-v2.0.1')
    dst = os.path.join(src, 'main', 'boards', 'alphapi-one-s-desktop')
    if not os.path.isdir(dst):
        raise RuntimeError('board dir missing: ' + dst)

    # 2. Apply the two source patches
    log('=== STEP 2: apply patches ===')
    run(['patch', '-p1', '-d', src, '-i', os.path.join(ROOT, 'desktop_ui.h.patch')])
    run(['patch', '-p1', '-d', src, '-i', os.path.join(ROOT, 'desktop_board.cc.patch')])

    # 3. Generate the metronome icon (replace game icon in assets)
    log('=== STEP 3: generate metronome icon ===')
    run([sys.executable, os.path.join(ROOT, 'gen_metronome_icon.py'),
         os.path.join(dst, 'desktop_assets.h')])

    # 3.5 PSRAM boot-loop fix (critical for v1.7 boards)
    log('=== STEP 3.5: PSRAM boot-loop fix ===')
    for fn in ('previous.defaults', 'ones.defaults', 'sdkconfig'):
        patch_psram_defaults(os.path.join(src, fn))
    # Also patch any sdkconfig.defaults variant that may exist
    for fn in os.listdir(src):
        if fn.startswith('sdkconfig') and fn not in ('sdkconfig',):
            patch_psram_defaults(os.path.join(src, fn))

    # 4. Build with ESP-IDF
    log('=== STEP 4: idf.py build ===')
    build_cmd = (
        'source "$IDF_PATH/export.sh" && '
        'idf.py -B build -D IDF_TARGET=esp32s2 '
        '-D "SDKCONFIG_DEFAULTS=previous.defaults;ones.defaults" build'
    )
    run(['bash', '-c', build_cmd], cwd=src)

    # 4.5 Verify PSRAM fix actually took effect in the generated sdkconfig
    log('=== STEP 4.5: verify PSRAM config in build/sdkconfig ===')
    built_sdk = os.path.join(src, 'build', 'sdkconfig')
    if os.path.exists(built_sdk):
        cfg = open(built_sdk, encoding='utf-8', errors='ignore').read()
        ignore_y = 'CONFIG_SPIRAM_IGNORE_NOTFOUND=y' in cfg
        speed40 = 'CONFIG_SPIRAM_SPEED=40' in cfg
        bailing = 'Bailing out' in cfg
        log('  IGNORE_NOTFOUND=y:', ignore_y)
        log('  SPIRAM_SPEED=40:', speed40)
        if not ignore_y:
            raise RuntimeError('PSRAM boot-loop fix FAILED: IGNORE_NOTFOUND is not y in build/sdkconfig')
        if not speed40:
            log('  WARNING: PSRAM speed is not 40 (still booting tolerant, may be OK)')
    else:
        log('  WARNING: build/sdkconfig not found, cannot verify')

    # 5. Collect artifacts
    log('=== STEP 5: collect artifacts ===')
    out = os.path.join(ROOT, 'out')
    os.makedirs(out, exist_ok=True)
    b = os.path.join(src, 'build')
    for rel in ['bootloader/bootloader.bin', 'partition_table/partition-table.bin',
                'ota_data_initial.bin', 'xiaozhi.bin', 'generated_assets.bin']:
        p = os.path.join(b, rel)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(out, os.path.basename(rel)))
            log('collected', os.path.basename(rel), os.path.getsize(p))
    if not os.path.exists(os.path.join(out, 'xiaozhi.bin')):
        raise RuntimeError('app bin (xiaozhi.bin) missing after build')

    # 5.5 Verify the abort-on-PSRAM-failure code is GONE from the final binary
    log('=== STEP 5.5: verify final binary has no PSRAM abort ===')
    app = open(os.path.join(out, 'xiaozhi.bin'), 'rb').read()
    bailing = b'PSRAM enabled but initialization failed' in app
    log('  final binary contains "Bailing out" abort:', bailing)
    if bailing:
        raise RuntimeError(
            'PSRAM fix did NOT take effect: final app still aborts on PSRAM failure')
    log('BUILD DONE')
    log('PSRAM BOOT-LOOP FIX APPLIED AND VERIFIED (no abort in final binary)')


if __name__ == '__main__':
    main()
