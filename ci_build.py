# -*- coding: utf-8 -*-
"""Cloud build driver: download upstream source, apply patches, build firmware.
Designed to run inside espressif/idf:release-v6.1 on GitHub Actions.
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

    # 4. Build with ESP-IDF
    log('=== STEP 4: idf.py build ===')
    build_cmd = (
        'source "$IDF_PATH/export.sh" && '
        'idf.py -B build -D IDF_TARGET=esp32s2 '
        '-D "SDKCONFIG_DEFAULTS=previous.defaults;ones.defaults" build'
    )
    run(['bash', '-c', build_cmd], cwd=src)

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
    log('BUILD DONE')


if __name__ == '__main__':
    main()
