"""Validated elementary diagrams. No model calls, guessed givens, or solved labels.

Parse only complete supported setups into numerical specs; return None for anything
else so the existing reference-guided generator can handle it. Geometry is computed
from the spec, never from model-authored coordinates. Inputs are normalized by app.py.
"""
import math
import re

NUM = r"[-+]?\d+(?:\.\d+)?"


def _n(value):
    return format(float(value), '.6g')


def _label(value, unit=''):
    return _n(value) + (r'\,\mathrm{' + unit + '}' if unit else '')


def _result(kind, spec, body):
    return {'template': kind, 'parameters': spec,
            'tikz': '\\begin{tikzpicture}\n' + body + '\n\\end{tikzpicture}'}


def _triangle(text):
    name = re.search(r'(?i:triangle)\s+([A-Z]{3})\b', text)
    right = re.search(r'(?i:right[- ]angled at|right angle at)\s+([A-Z])\b', text)
    if not name or not right or right[1] not in name[1] or len(set(name[1])) != 3:
        return None
    if re.search(r'median|bisector|altitude|incircle|circumcircle|rotation|reflect', text, re.I):
        return None
    a = right[1]
    b, c = [v for v in name[1] if v != a]
    # Respect explicit horizontal/vertical instructions when supplied.
    if re.search(rf'{a}{b}\s+horizontally|{b}{a}\s+horizontally|{a}{c}\s+vertically|{c}{a}\s+vertically', text, re.I):
        b, c = c, b
    def length(v):
        matches = re.findall(rf'\b(?:{a}{v}|{v}{a})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b', text)
        return matches[0] if matches and len(set(matches)) == 1 else None
    vb, vc = length(b), length(c)
    if not vb or not vc or vb[1] != vc[1]:
        return None
    vertical, horizontal = float(vb[0]), float(vc[0])
    if not (0 < vertical < 1e5 and 0 < horizontal < 1e5 and .15 <= vertical / horizontal <= 6):
        return None
    # A separately given hypotenuse or an extra construction needs the general path.
    if re.search(rf'\b(?:{b}{c}|{c}{b})\s*=\s*{NUM}', text):
        return None
    s = 4.2 / max(vertical, horizontal)
    x, y = _n(horizontal*s), _n(vertical*s)
    unknown = re.search(rf'(?i:label)\s+(?:{b}{c}|{c}{b})\s+(?i:as)\s+([a-z])\b', text)
    hyp = unknown[1] if unknown else '?'
    return _result('right_triangle_given_legs', dict(vertices=[a,b,c], vertical=vertical, horizontal=horizontal, unit=vb[1]), rf'''
\coordinate ({a}) at (0,0); \coordinate ({b}) at (0,{y}); \coordinate ({c}) at ({x},0);
\draw[cp line] ({a})--({b})--({c})--cycle;
\pic[draw=black,angle radius=4mm] {{right angle={c}--{a}--{b}}};
\node[below left] at ({a}) {{${a}$}}; \node[above left] at ({b}) {{${b}$}}; \node[below right] at ({c}) {{${c}$}};
\path ({a})--({b}) node[midway,left] {{${_label(vertical,vb[1])}$}};
\path ({a})--({c}) node[midway,below] {{${_label(horizontal,vc[1])}$}};
\path ({b})--({c}) node[midway,above right] {{${hyp}$}};''')


def _points(text):
    if not re.search(r'midpoint', text, re.I) or re.search(r'circle|triangle|perpendicular|bisector|reflect|translate|rotate', text, re.I):
        return None
    points = re.findall(rf'\b([A-Z])\s*\(\s*({NUM})\s*,\s*({NUM})\s*\)', text)
    if len(points) != 2 or points[0][0] == points[1][0]:
        return None
    values = [(p,float(x),float(y)) for p,x,y in points]
    if values[0][1:] == values[1][1:] or any(abs(v)>1000 for _,x,y in values for v in (x,y)):
        return None
    bounds = re.search(rf'both axes from\s*({NUM})\s*to\s*({NUM})', text, re.I)
    lo, hi = (float(bounds[1]),float(bounds[2])) if bounds else (math.floor(min(0,*(v for _,x,y in values for v in (x,y))))-1, math.ceil(max(0,*(v for _,x,y in values for v in (x,y))))+1)
    if not lo < hi or hi-lo > 40 or any(not lo <= v <= hi for _,x,y in values for v in (x,y)):
        return None
    marks = '\n'.join(rf'\addplot[only marks,mark=*,mark size=1.5pt] coordinates {{({_n(x)},{_n(y)})}};\node[above right,font=\small] at (axis cs:{_n(x)},{_n(y)}) {{${p}({_n(x)},{_n(y)})$}};' for p,x,y in values)
    coords = ' '.join(f'({_n(x)},{_n(y)})' for _,x,y in values)
    return _result('coordinate_segment',dict(points=values,bounds=[lo,hi]),rf'''
\begin{{axis}}[width=7cm,height=7cm,axis equal image,axis lines=middle,xlabel=$x$,ylabel=$y$,
xmin={_n(lo)},xmax={_n(hi)},ymin={_n(lo)},ymax={_n(hi)},xtick distance=1,ytick distance=1,
tick label style={{font=\small}},grid=major,grid style={{gray!25,thin}},clip=false]
\addplot[cp line] coordinates {{{coords}}};
{marks}
\end{{axis}}''')


def _tangent(text):
    if not re.search(r'circle',text,re.I) or not re.search(r'tangent',text,re.I):
        return None
    centre = re.search(r'cent(?:re|er)\s+([A-Z])\b',text,re.I)
    radius = re.search(rf'radius\s*({NUM})\s*(cm|mm|km|m)?\b',text,re.I)
    tangent = re.search(r'\b([A-Z])([A-Z])\s+is tangent',text)
    if not centre or not radius or not tangent or re.search(r'two tangents|sector|chord|arc|second circle',text,re.I):
        return None
    o, p, t = centre[1].upper(), tangent[1], tangent[2]
    if len({o,p,t}) != 3:
        return None
    distance = re.search(rf'\b(?:{o}{p}|{p}{o})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b',text)
    if not distance or distance[2] != radius[2]:
        return None
    r,d = float(radius[1]),float(distance[1])
    if not 0 < r < d < 1e5 or not 1.1 < d/r < 8:
        return None
    tx,ty = r*r/d, r*math.sqrt(d*d-r*r)/d
    s = 5/(r+d)
    unknown = re.search(rf'\b{p}{t}\s*=\s*([a-z])\b',text)
    lab = unknown[1] if unknown else '?'
    return _result('circle_external_tangent',dict(radius=r,distance=d,tangent_point=[tx,ty],vertices=[o,p,t]),rf'''
\coordinate ({o}) at (0,0);\coordinate ({p}) at ({_n(d*s)},0);\coordinate ({t}) at ({_n(tx*s)},{_n(ty*s)});
\draw[cp line] ({o}) circle[radius={_n(r*s)}];
\draw[cp line] ({o})--({p}) node[pos=.72,below] {{${_label(d,distance[2])}$}};
\draw[cp line] ({o})--({t}) node[midway,left] {{${_label(r,radius[2])}$}};
\draw[cp line] ({t})--({p}) node[midway,above right] {{${lab}$}};
\pic[draw=black,angle radius=3mm] {{right angle={o}--{t}--{p}}};
\node[below left] at ({o}) {{${o}$}};\node[right] at ({p}) {{${p}$}};\node[above] at ({t}) {{${t}$}};''')


def _forces(text):
    if not re.search(r'block',text,re.I) or not re.search(r'four forces',text,re.I):
        return None
    if re.search(r'incline|ramp|angle|friction coefficient|pulley',text,re.I):
        return None
    matches = re.findall(rf'({NUM})\s*(?:N|newtons?)\s+(upward|downward|to the right|to the left)\b',text,re.I)
    forces = {direction.lower():float(value) for value,direction in matches}
    if len(matches)!=4 or set(forces)!={'upward','downward','to the right','to the left'} or any(not 0 < v < 1e6 for v in forces.values()):
        return None
    body = r'\draw[cp line] (-.6,-.4) rectangle (.6,.4);\draw[cp line] (-2,-.4)--(2,-.4);'+'\n'
    for direction,start,delta,anchor in [
        ('upward',(0,.4),(0,1),'above'),('downward',(0,-.4),(0,-1),'below'),
        ('to the right',(.6,0),(1,0),'right'),('to the left',(-.6,0),(-1,0),'left')]:
        length = .65 + .75*forces[direction]/max(forces.values())
        end = (start[0]+delta[0]*length,start[1]+delta[1]*length)
        body += rf'\draw[cp line,->] ({start[0]},{start[1]})--({_n(end[0])},{_n(end[1])}) node[{anchor}] {{${_label(forces[direction],"N")}$}};'+'\n'
    return _result('block_four_forces',forces,body)


def generate(text):
    """Return an exact supported numerical setup, otherwise leave custom generation intact."""
    for parser in (_triangle, _points, _tangent, _forces):
        hit = parser(text)
        if hit:
            return hit
    return None
