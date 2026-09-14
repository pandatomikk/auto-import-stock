"""Conversion atomique des photos produit, transparence et profil ICC conservés."""
from pathlib import Path
from PIL import Image, ImageOps, ImageChops, ImageFilter

PIPELINE_VERSION = "trim-light-background-v1"

def trim_product_background(image):
    """Crop large pale studio margins; leave coloured backgrounds and scenes alone."""
    probe = image.copy()
    probe.thumbnail((600, 600), Image.Resampling.LANCZOS)
    width, height = probe.size
    if min(width, height) < 32:
        return image
    if image.mode == "RGBA" and image.getextrema()[3][0] < 255:
        mask = probe.getchannel("A").point(lambda value: 255 if value > 8 else 0)
    else:
        rgb = probe.convert("RGB")
        points = [(x, y) for x in (0, width//2, width-1) for y in (0, height-1)] + [(0, height//2), (width-1, height//2)]
        samples = [rgb.getpixel(point) for point in points]
        if any(min(pixel) < 225 or max(pixel)-min(pixel) > 14 for pixel in samples):
            return image
        background = tuple(min(pixel[channel] for pixel in samples) for channel in range(3))
        difference = ImageChops.subtract(Image.new("RGB", rgb.size, background), rgb)
        red, green, blue = difference.split()
        mask = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(lambda value: 255 if value > 12 else 0)
        mask = mask.filter(ImageFilter.MedianFilter(3))
    bounds = mask.getbbox()
    if not bounds:
        return image
    left, top, right, bottom = bounds
    if (right-left)*(bottom-top) < width*height*0.001:
        return image
    margin = max(8, round(max(right-left, bottom-top)*0.06))
    left, top = max(0,left-margin), max(0,top-margin)
    right, bottom = min(width,right+margin), min(height,bottom+margin)
    if (right-left)*(bottom-top) >= width*height*0.90:
        return image
    sx, sy = image.width/width, image.height/height
    return image.crop((int(left*sx),int(top*sy),min(image.width,round(right*sx)),min(image.height,round(bottom*sy))))


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
            original_size = im.size
            im = trim_product_background(im)
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
                'width':dimensions[0],'height':dimensions[1], 'original_width':original_size[0], 'original_height':original_size[1]}
    finally:
        temporary.unlink(missing_ok=True)
