"""Check resource references and WCAG text contrast of the two explicit palettes."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
src=Path('android/app/src/main/java/in/weathergpt/MainActivity.kt').read_text(encoding='utf-8')
keys={e.attrib['name'] for e in ET.parse('android/app/src/main/res/values/strings.xml').getroot()}
missing=set(re.findall(r'R\.string\.(\w+)',src))-keys
assert not missing,missing

def lum(s):
    rgb=[int(s[i:i+2],16)/255 for i in (0,2,4)]
    lin=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in rgb]
    return sum(a*b for a,b in zip(lin,[.2126,.7152,.0722]))
for name in ['Light','Dark']:
    line=next(l for l in src.splitlines() if l.startswith('private val '+name+'='))
    colors=dict(re.findall(r'(\w+)=Color\(0xFF([0-9A-F]{6})\)',line))
    colors.update(dict((k,'FFFFFF') for k in re.findall(r'(\w+)=Color.White',line)))
    for fg,bg in [('onPrimary','primary'),('onSurface','surface'),('onSurfaceVariant','surfaceVariant'),('onPrimaryContainer','primaryContainer')]:
        a,b=sorted([lum(colors[fg]),lum(colors[bg])])
        ratio=(b+.05)/(a+.05)
        assert ratio>=4.5,(name,fg,bg,ratio)
        print(name,fg,bg,round(ratio,2))
print('Theme contrast and resource references passed')
