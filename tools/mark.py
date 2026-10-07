from PIL import Image, ImageDraw
S='.'
logo=Image.open('assets/logo.png').convert('RGBA')
PINK=(235,130,124,255); BLUE=(119,170,209,255)
def apply(src,dst,rel=0.17,margin=0.03,thick=0.007,gap=0.012):
    im=Image.open(src).convert('RGBA')
    W,H=im.size
    w=int(W*rel); h=int(logo.size[1]*w/logo.size[0])
    lg=logo.resize((w,h),Image.LANCZOS)
    m=int(W*margin); t=max(4,int(W*thick)); g=int(W*gap)
    d=ImageDraw.Draw(im)
    # bottom-left logo + sky-blue line beside it, running to the right margin
    bx,by=m,H-h-m
    im.alpha_composite(lg,(bx,by))
    cy=by+h//2
    d.rounded_rectangle([bx+w+g,cy-t//2,W-m,cy+t//2],radius=t//2,fill=BLUE)
    # top-right logo + pink line beside it, running to the left margin
    tx,ty=W-w-m,m
    im.alpha_composite(lg,(tx,ty))
    cy=ty+h//2
    d.rounded_rectangle([m,cy-t//2,tx-g,cy+t//2],radius=t//2,fill=PINK)
    im.convert('RGB').save(dst,quality=90)
if __name__=='__main__':
    apply('/home/claude/nagham-images/img/IMG_0185.jpg',S+'/s3_0185.jpg')
    apply('/home/claude/nagham-images/img/IMG_0301.jpg',S+'/s3_0301.jpg')
