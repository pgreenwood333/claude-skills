from PIL import Image, ImageDraw, ImageFont
import sys, os, json
FD="/Library/Fonts"; SY="/System/Library/Fonts"
def SERIF(s): return ImageFont.truetype(f"{SY}/Palatino.ttc", s, index=0)
def SF(w,s): return ImageFont.truetype(f"{FD}/SF-Pro-Display-{w}.otf", s)
LAV=(0xB8,0x9D,0xF2); WHITE=(255,255,255); GOLD=(0xD8,0xA5,0x20)  # darker gold
# which chip indices are BOLD (stick out); rest regular
BOLD_IDX={0,2,4}
def bold(d,xy,t,f,fill,anchor="mm",sp=3):
    x,y=xy
    for dx,dy in [(sp,sp),(-sp,sp),(sp,-sp),(-sp,-sp)]: d.text((x+dx,y+dy),t,font=f,fill=(0,0,14),anchor=anchor)
    for dx in (-1,0,1):
        for dy in (-1,0,1): d.text((x+dx,y+dy),t,font=f,fill=fill,anchor=anchor)
def render(base,out,l1,l2,chips):
    im=Image.open(base).convert("RGB"); W,H=im.size; d=ImageDraw.Draw(im)
    def fit(text,fn,maxw,start):
        s=start
        while s>40 and d.textlength(text,font=fn(s))>maxw: s-=2
        return fn(s)
    # TITLE (larger)
    f1=fit(l1,SERIF,1230,132); bold(d,(W//2,238),l1,f1,WHITE,"ma")
    f2=fit(l2,SERIF,1240,132); bold(d,(W//2,238+int(f1.size*1.12)),l2,f2,LAV,"ma")
    # CHIPS: all darker gold, alternate weight; pick largest size <=74 that fits both rows in 1250
    sep="   ·   "
    def rowwidth(items,size):
        tot=0
        for i,c in enumerate(items):
            f=SF("Heavy" if i in BOLD_IDX else "Medium",size); tot+=d.textlength(c,font=f)
        tot+=d.textlength(sep,font=SF("Medium",size))*(len(items)-1); return tot
    size=74
    while size>48 and (rowwidth(chips[:3],size)>1250 or rowwidth(chips[3:6],size)>1250): size-=2
    def row(items,y,base_i):
        widths=[d.textlength(c,font=SF("Heavy" if (base_i+i) in BOLD_IDX else "Medium",size)) for i,c in enumerate(items)]
        sepf=SF("Medium",size); sepw=d.textlength(sep,font=sepf)
        total=sum(widths)+sepw*(len(items)-1); x=W/2-total/2
        for i,c in enumerate(items):
            idx=base_i+i; f=SF("Heavy" if idx in BOLD_IDX else "Medium",size)
            for dx,dy in [(2,2),(-2,2),(2,-2),(-2,-2)]: d.text((x+dx,y+dy),c,font=f,fill=(0,0,12),anchor="lm")
            d.text((x,y),c,font=f,fill=GOLD,anchor="lm"); x+=widths[i]
            if i<len(items)-1: d.text((x,y),sep,font=sepf,fill=(150,140,170),anchor="lm"); x+=sepw
    gap=int(size*1.9)
    row(chips[:3],2500,0); row(chips[3:6],2500+gap,3)
    os.makedirs(os.path.dirname(out),exist_ok=True); im.save(out); return im.size
if __name__=="__main__":
    a=json.load(open(sys.argv[1])); print(render(**a))
