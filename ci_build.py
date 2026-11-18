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

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd, cwd=None):
    print('$', ' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=cwd)


def main():
    os.chdir(ROOT)

    # 1. Download upstream v2.0.1 source
    url = ('https://raw.githubusercontent.com/mastomato/AlphaPi-OneS-4in1/'
           'main/source/AlphaPi-OneS-4in1-source-v2.0.1.zip')
    print('Downloading upstream source...', flush=True)
    urllib.request.urlretrieve(url, 'src.zip')
    with zipfile.ZipFile('src.zip') as z:
        z.extractall('src')

    src = os.path.join(ROOT, 'src', 'AlphaPi-OneS-4in1-source-v2.0.1')
    dst = os.path.join(src, 'main', 'boards', 'alphapi-one-s-desktop')

    # 2. Apply the two source patches
    run(['patch', '-p1', '-d', src, '-i', os.path.join(ROOT, 'desktop_ui.h.patch')])
    run(['patch', '-p1', '-d', src, '-i', os.path.join(ROOT, 'desktop_board.cc.patch')])

    # 3. Generate the metronome icon (replace game icon in assets)
    run([sys.executable, os.path.join(ROOT, 'gen_metronome_icon.py'),
         os.path.join(dst, 'desktop_assets.h')])

    # 4. Build with ESP-IDF
    build_cmd = (
        'source "$IDF_PATH/export.sh" && '
        'idf.py -B build -D IDF_TARGET=esp32s2 '
        '-D "SDKCONFIG_DEFAULTS=previous.defaults;ones.defaults" build'
    )
    run(['bash', '-c', build_cmd], cwd=src)

    # 5. Collect artifacts
    out = os.path.join(ROOT, 'out')
    os.makedirs(out, exist_ok=True)
    b = os.path.join(src, 'build')
    for rel in ['bootloader/bootloader.bin', 'partition_table/partition-table.bin',
                'ota_data_initial.bin', 'xiaozhi.bin', 'generated_assets.bin']:
        p = os.path.join(b, rel)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(out, os.path.basename(rel)))
            print('collected', os.path.basename(rel), flush=True)
    if not os.path.exists(os.path.join(out, 'xiaozhi.bin')):
        raise RuntimeError('app bin (xiaozhi.bin) missing after build')
    print('BUILD DONE', flush=True)


if __name__ == '__main__':
    main()
