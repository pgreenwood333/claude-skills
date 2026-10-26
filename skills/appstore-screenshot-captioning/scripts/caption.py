from PIL import Image, ImageDraw, ImageFont
import sys, json, os
FD="/Library/Fonts"
def TITLE(s): return ImageFont.truetype(f"{FD}/SF-Pro-Display-Heavy.otf", s)
def SUB(s):   return ImageFont.truetype(f"{FD}/SF-Pro-Display-Medium.otf", s)
PURPLE=(0x99,0x99,0xF4); WHITE=(255,255,255)
def render(base_path, out_path, words, subtitle, title_size=116, sub_size=54,
           max_w=1240, center_y=400):
    words=[(w,tuple(c)) for w,c in words]
    im=Image.open(base_path).convert("RGB"); W,H=im.size; d=ImageDraw.Draw(im)
    tf=TITLE(title_size); sf=SUB(sub_size)
    sp=" "
    # wrap words (word,color) into lines fitting max_w
    lines=[]; cur=[]
    def linew(ws): return d.textlength(sp.join(w for w,_ in ws), font=tf)
    for w in words:
        if cur and linew(cur+[w])>max_w: lines.append(cur); cur=[w]
        else: cur.append(w)
    if cur: lines.append(cur)
    pitch=int(title_size*1.18); gap=90; subpitch=int(sub_size*1.25)
    # wrap subtitle
    subs=[]; cw=[]
    for word in subtitle.split():
        if cw and d.textlength(sp.join(cw+[word]),font=sf)>1180: subs.append(sp.join(cw)); cw=[word]
        else: cw.append(word)
    if cw: subs.append(sp.join(cw))
    total = len(lines)*pitch + gap + len(subs)*subpitch
    y = center_y - total//2
    for ws in lines:
        tot=d.textlength(sp.join(w for w,_ in ws),font=tf)
        x=(W-tot)//2
        for i,(w,c) in enumerate(ws):
            d.text((x,y),w,font=tf,fill=c)
            x+=d.textlength(w+(sp if i<len(ws)-1 else ""),font=tf)
        y+=pitch
    y+=gap-pitch+int(title_size*0.9)
    for sline in subs:
        d.text((W//2,y),sline,font=sf,fill=WHITE,anchor="ma"); y+=subpitch
    os.makedirs(os.path.dirname(out_path),exist_ok=True); im.save(out_path); return im.size
if __name__=="__main__":
    spec=json.load(open(sys.argv[1])); print(render(**spec))
