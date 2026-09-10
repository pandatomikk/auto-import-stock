"""Installation utilisateur Windows. Ne supprime pas les configurations existantes."""
import os,sys,shutil,subprocess,json,tempfile,urllib.request
from pathlib import Path

def copy_application(source, target):
    source, target = Path(source), Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in ['client.py', 'lancer.py', 'convertisseur.py', 'requirements.txt', 'README.md', 'LICENSE', 'core', 'schemas', 'profiles']:
        src, dst = source / name, target / name
        if src.is_dir():
            for file in src.rglob('*'):
                if not file.is_file() or '__pycache__' in file.parts:
                    continue
                dest = dst / file.relative_to(src)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
        elif src.is_file():
            shutil.copy2(src, dst)
    for name in ['profiles', 'rules', 'adapters']:
        (target / 'private' / name).mkdir(parents=True, exist_ok=True)
    # Only operational private content is installed, never tests or backups.
    for name in ['profiles', 'rules', 'adapters']:
        src = source / 'private' / name
        for file in src.rglob('*'):
            if not file.is_file() or '__pycache__' in file.parts:
                continue
            dest = target / 'private' / name / file.relative_to(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if name in {'profiles', 'rules'}:
                legacy = target / 'configs' / file.name
                existing = dest if dest.exists() else legacy if legacy.exists() else None
                if existing:
                    if name == 'rules':
                        if existing != dest:
                            shutil.copy2(existing, dest)
                        continue
                    current = json.loads(existing.read_text(encoding='utf-8'))
                    template = json.loads(file.read_text(encoding='utf-8'))
                    # Preserve business mappings while migrating adapter routing.
                    for key in ['workflow', 'default', 'product_rules']:
                        if key == 'product_rules' and key in current:
                            continue
                        if key in template:
                            current[key] = template[key]
                    for key in ['mode', 'directory', 'service_label', 'filename_pattern']:
                        if key in template.get('images', {}):
                            current.setdefault('images', {})[key] = template['images'][key]
                    if template.get('supplier_descriptions', {}).get('adapter'):
                        current.setdefault('supplier_descriptions', {})['adapter'] = template['supplier_descriptions']['adapter']
                    dest.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
                    continue
            shutil.copy2(file, dest)

def find_tool(name):
    existing=shutil.which(name)
    if existing:return Path(existing)
    roots=[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Tesseract-OCR',
      Path(os.environ['LOCALAPPDATA'])/'Programs'/'Tesseract-OCR',
      Path(os.environ['LOCALAPPDATA'])/'Microsoft'/'WinGet'/'Links']
    for root in roots:
        p=root/(name+'.exe')
        if p.exists():return p
    packages=Path(os.environ['LOCALAPPDATA'])/'Microsoft'/'WinGet'/'Packages'
    for root in packages.glob('oschwartz10612.Poppler_*'):
        for p in root.rglob(name+'.exe'):return p
    return None

def main():
    if os.name!='nt':raise RuntimeError('Cet installateur concerne Windows uniquement.')
    source=Path(__file__).resolve().parent
    target=Path(os.environ['LOCALAPPDATA'])/'ZPSI'/'Catalogue'
    print('Verification des composants PDF/OCR...')
    tools={name:find_tool(name) for name in ['pdfinfo','pdftotext','pdftoppm','tesseract']}
    absent=[name for name,path in tools.items() if path is None]
    if absent:raise RuntimeError('Outils introuvables : '+', '.join(absent)+'. Verifier les installations WinGet puis relancer.')
    for name,path in tools.items():
        subprocess.run([str(path),'--version' if name=='tesseract' else '-v'],check=True,capture_output=True,timeout=30)
    print('Copie de l’application et conservation des profils...')
    copy_application(source,target)
    py=target/'.venv'/'Scripts'/'python.exe'
    if not py.exists():subprocess.run([sys.executable,'-m','venv',str(target/'.venv')],check=True)
    subprocess.run([str(py),'-m','pip','install','--disable-pip-version-check','-r',str(target/'requirements.txt')],check=True)
    subprocess.run([str(py),'-c','import tkinter,openpyxl,gdown; from PIL import features; assert features.check("webp")'],check=True)
    subprocess.run([str(py),'-c','from core.shop_connection import initialize_storage, load_settings; initialize_storage(); load_settings()'],cwd=target,check=True)
    print('Installation des langues OCR...')
    tessdata=target/'tessdata';tessdata.mkdir(exist_ok=True)
    for language in ['fra','eng']:
        output=tessdata/(language+'.traineddata')
        if not output.exists():
            part=output.with_suffix('.part')
            urllib.request.urlretrieve('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/'+language+'.traineddata',part)
            part.replace(output)
    env={**os.environ,'TESSDATA_PREFIX':str(tessdata)}
    langs=subprocess.run([str(tools['tesseract']),'--list-langs'],env=env,check=True,capture_output=True,text=True).stdout
    if not all(x in langs.splitlines() for x in ['fra','eng']):raise RuntimeError('Langues OCR non disponibles')
    (target/'runtime_windows.json').write_text(json.dumps({'paths':list(dict.fromkeys(str(p.parent) for p in tools.values())),'tessdata':str(tessdata)}),encoding='utf-8')
    print('Verification OCR de bout en bout...')
    with tempfile.TemporaryDirectory() as tmp:
        png=Path(tmp)/'test.png'
        subprocess.run([str(py),'-c','from PIL import Image; import sys; Image.new("RGB",(200,80),"white").save(sys.argv[1])',str(png)],check=True)
        subprocess.run([str(tools['tesseract']),str(png),'stdout','-l','fra'],env=env,check=True,capture_output=True,timeout=30)
    # Let Windows resolve Desktop/Start Menu, including redirected folders.
    script=target/'creer-raccourcis.vbs'
    quote=lambda text:'"'+str(text).replace('"','""')+'"'
    lines=['Set s = CreateObject("WScript.Shell")']
    for location in ['Desktop','Programs']:
        lines+=['Set l = s.CreateShortcut(s.SpecialFolders('+quote(location)+') & "\\ZPSI Catalogue.lnk")',
          'l.TargetPath = '+quote(py.with_name('pythonw.exe')),
          'l.Arguments = '+quote('"'+str(target/'client.py')+'"'),
          'l.WorkingDirectory = '+quote(target),'l.Save']
    script.write_text('\n'.join(lines),encoding='utf-16')
    subprocess.run(['cscript.exe','//Nologo',str(script)],check=True)
    print('Application installee dans '+str(target))
    print('Profils modifiables : '+str(target/'private'/'profiles'))
if __name__=='__main__':
    try:main()
    except Exception as error:
        print('INSTALLATION NON TERMINEE : '+str(error));sys.exit(1)
