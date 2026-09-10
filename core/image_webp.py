"""Conversion atomique des photos produit, transparence et profil ICC conservés."""
from pathlib import Path
from PIL import Image, ImageOps

def optimize_webp(source, target):
    source,target=Path(source),Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.webp.tmp')
    try:
        with Image.open(source) as original:
            if getattr(original,'n_frames',1)>1:
                raise ValueError('Image animée non convertie automatiquement')
            profile=original.info.get('icc_profile')
            im=ImageOps.exif_transpose(original)
            im=im.convert('RGBA' if 'A' in im.getbands() or 'transparency' in im.info else 'RGB')
            im.thumbnail((1600,1600),Image.Resampling.LANCZOS)
            options={'format':'WEBP','quality':85,'method':6}
            if profile:options['icc_profile']=profile
            im.save(temporary,**options)
            dimensions=im.size
        with Image.open(temporary) as check:
            if check.format!='WEBP':raise ValueError('Conversion WebP invalide')
            check.verify()
        temporary.replace(target)
        return {'source_bytes':source.stat().st_size,'output_bytes':target.stat().st_size,
                'width':dimensions[0],'height':dimensions[1]}
    finally:
        temporary.unlink(missing_ok=True)
