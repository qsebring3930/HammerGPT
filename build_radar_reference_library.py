"""Render curated, uncertain image-space radar observations for review."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import binary_fill_holes,label
ROOT=Path(__file__).resolve().parent

def build(out):
 if out.exists():raise ValueError('Use a new output directory to preserve previous annotations')
 out.mkdir(parents=True)
 library=json.loads((ROOT/'config/radar-reference-observations.json').read_text())
 clean=Image.new('RGB',(1800,2050),'#17202b');annotated=clean.copy()
 for index,obs in enumerate(library['observations']):
  source=ROOT/obs['source']
  if hashlib.sha256(source.read_bytes()).hexdigest()!=obs['sha256']:raise ValueError('Source changed: '+str(source))
  im=Image.open(source).convert('RGB');a=np.asarray(im);lum=a.mean(2);chroma=a.max(2).astype(float)-a.min(2)
  mask=(lum>45)&(lum<210)&((chroma>10)|(lum>55))
  if obs['id']=='R13':mask[:]=False
  holes=binary_fill_holes(mask)&~mask;labels,n=label(holes);large=np.zeros_like(holes)
  for k in range(1,n+1):
   region=labels==k
   if region.sum()>im.width*im.height*.003:large|=region
  Image.fromarray(mask.astype('uint8')*255).save(out/obs['approximate_regions']['foreground'])
  Image.fromarray(large.astype('uint8')*255).save(out/obs['approximate_regions']['enclosed_voids'])
  overlay=im.copy();d=ImageDraw.Draw(overlay)
  for sample in obs['samples']:
   color={'P':'#ffdf65','W':'#57dbe7','M':'#ff8366'}[sample['id'][-1]]
   pts=[(x*im.width,y*im.height) for x,y in sample['normalized_polygon']]
   d.line(pts+[pts[0]],fill=color,width=max(2,im.width//300));d.text(pts[0],sample['id'],fill=color)
  for j,(x,y) in enumerate(obs['entrance_hints']):
   x*=im.width;y*=im.height;r=max(5,im.width//70)
   d.ellipse((x-r,y-r,x+r,y+r),outline='#b9ff91',width=3);d.text((x+r,y),f'E{j+1}?',fill='#b9ff91')
  overlay.save(out/obs['overlay'])
  for canvas,picture in [(clean,im),(annotated,overlay)]:
   thumb=picture.copy();thumb.thumbnail((435,370));x=index%4*450+(450-thumb.width)//2;y=index//4*410
   canvas.paste(thumb,(x,y+25));ImageDraw.Draw(canvas).text((index%4*450+8,y+5),obs['id']+' '+source.name,fill='white')
 clean.save(out/'contact-sheet.png');annotated.save(out/'annotation-contact-sheet.png')
 (out/'library.json').write_text(json.dumps(library,indent=2))
 (out/'README.md').write_text('Image-space review hypotheses only. P yellow: coarse chamber/court; W cyan: passage; M orange: likely footprint/void; E green: uncertain entrance hint. Masks are brightness/chroma estimates, not NAV or collision. R13 checkerboard segmentation disabled. No HU scale, height, timing or overlapping-floor topology is inferred.\n')
 print('Rendered',len(library['observations']),'references to',out)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();build(args.output)
