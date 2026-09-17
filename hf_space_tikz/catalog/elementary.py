"""Validated elementary diagrams. No model calls, guessed givens, or solved labels.

Parse only complete supported setups into numerical specs; return None for anything
else so the existing reference-guided generator can handle it. Geometry is computed
from the spec, never from model-authored coordinates. Inputs are normalized by app.py.
"""
import math
import re

NUM = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"


def _n(value):
    return format(float(value), '.6g')


def _label(value, unit=''):
    return _n(value) + (r'\,\mathrm{' + unit + '}' if unit else '')


def _result(kind, spec, body):
    return {'template': kind, 'parameters': spec,
            'tikz': '\\begin{tikzpicture}\n' + body + '\n\\end{tikzpicture}'}


def _consistent(matches):
    """Accept repeated numerical givens, never pick one of conflicting values."""
    values = {(float(value), unit or '') for value, unit in matches}
    return next(iter(values)) if len(values) == 1 else None


def _unknown(text, side):
    labels = set(re.findall(rf'\b(?:{side}|{side[::-1]})\s*(?:=|(?i:as))\s*([a-z])\b', text))
    return next(iter(labels), '?') if len(labels) <= 1 else None


def _triangle(text):
    name = re.search(r'(?i:triangle)\s+([A-Z]{3})\b', text)
    right = re.search(r'(?i:right[- ]angled at|right angle at)\s+([A-Z])\b', text)
    if not name or not right or right[1] not in name[1] or len(set(name[1])) != 3:
        return None
    if len({frozenset(v) for v in re.findall(r'(?i:triangle)\s+([A-Z]{3})\b', text)}) != 1:
        return None
    if re.search(r'median|bisector|altitude|incircle|circumcircle|rotation|reflect', text, re.I):
        return None
    a = right[1]
    if len(set(re.findall(r'(?i:right[- ]angled at|right angle at)\s+([A-Z])\b', text))) != 1:
        return None
    b, c = [v for v in name[1] if v != a]
    # Respect explicit orientation, including the content model's "should be" form.
    orientations = {}
    for side, orientation in re.findall(r'\b([A-Z]{2})\s+(?:(?:should be|is)\s+)?(vertical(?:ly)?|horizontal(?:ly)?)\b', text):
        side = ''.join(sorted(side))
        orientation = orientation[:1]
        if side in orientations and orientations[side] != orientation:
            return None
        orientations[side] = orientation
    if orientations.get(''.join(sorted(a+b))) == 'h' or orientations.get(''.join(sorted(a+c))) == 'v':
        b,c = c,b
    if any(orientations.get(''.join(sorted(side)), expected) != expected for side,expected in [(a+b,'v'),(a+c,'h')]):
        return None
    def length(v):
        matches = re.findall(rf'\b(?:{a}{v}|{v}{a})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b', text)
        return _consistent(matches)
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
    hyp = _unknown(text, b+c)
    if hyp is None:
        return None
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
    unique = {}
    for p, x, y in points:
        coordinates = (float(x), float(y))
        if p in unique and unique[p] != coordinates:
            return None
        unique[p] = coordinates
    if len(unique) != 2:
        return None
    values = [(p,x,y) for p,(x,y) in unique.items()]
    if values[0][1:] == values[1][1:] or any(abs(v)>1000 for _,x,y in values for v in (x,y)):
        return None
    bounds = {(float(lo), float(hi)) for lo,hi in re.findall(rf'both axes from\s*({NUM})\s*to\s*({NUM})', text, re.I)}
    separate_bounds = re.findall(rf'([xy])\s*[- ]\s*axis\s+from\s*({NUM})\s*to\s*({NUM})', text, re.I)
    if separate_bounds and not bounds and {axis.lower() for axis,_,_ in separate_bounds} != {'x','y'}:
        return None
    bounds.update((float(lo),float(hi)) for _,lo,hi in separate_bounds)
    if len(bounds) > 1:
        return None
    lo, hi = next(iter(bounds)) if bounds else (math.floor(min(0,*(v for _,x,y in values for v in (x,y))))-1, math.ceil(max(0,*(v for _,x,y in values for v in (x,y))))+1)
    if not lo < hi or hi-lo > 40 or any(not lo <= v <= hi for _,x,y in values for v in (x,y)):
        return None
    # Keep labels away from the horizontal axis and its numbered ticks.
    marks = '\n'.join(rf'\addplot[only marks,mark=*,mark size=1.5pt] coordinates {{({_n(x)},{_n(y)})}};\node[{"below" if y < 0 else "above"} right,font=\small] at (axis cs:{_n(x)},{_n(y)}) {{${p}({_n(x)},{_n(y)})$}};' for p,x,y in values)
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
    radius = _consistent(re.findall(rf'radius\s*({NUM})\s*(cm|mm|km|m)?\b',text,re.I))
    tangent = re.search(r'\b([A-Z])([A-Z])\s+is tangent',text)
    if not centre or not radius or not tangent or re.search(r'two tangents|sector|chord|arc|second circle',text,re.I):
        return None
    o, p, t = centre[1].upper(), tangent[1], tangent[2]
    if len(set(re.findall(r'cent(?:re|er)\s+([A-Z])\b',text))) > 1 or len(set(re.findall(r'\b([A-Z]{2})\s+is tangent',text))) > 1:
        return None
    if len({o,p,t}) != 3:
        return None
    radius = _consistent([(str(radius[0]), radius[1])] + re.findall(rf'\b(?:{o}{t}|{t}{o})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b',text))
    distance = _consistent(re.findall(rf'\b(?:{o}{p}|{p}{o})\s*=\s*({NUM})\s*(cm|mm|km|m)?\b',text))
    if not radius or not distance or distance[1] != radius[1]:
        return None
    r,d = radius[0],distance[0]
    if not 0 < r < d < 1e5 or not 1.1 < d/r < 8:
        return None
    tx,ty = r*r/d, r*math.sqrt(d*d-r*r)/d
    s = 5/(r+d)
    lab = _unknown(text, p+t)
    if lab is None or re.search(rf'\b(?:{p}{t}|{t}{p})\s*=\s*{NUM}', text):
        return None
    return _result('circle_external_tangent',dict(radius=r,distance=d,tangent_point=[tx,ty],vertices=[o,p,t]),rf'''
\coordinate ({o}) at (0,0);\coordinate ({p}) at ({_n(d*s)},0);\coordinate ({t}) at ({_n(tx*s)},{_n(ty*s)});
\draw[cp line] ({o}) circle[radius={_n(r*s)}];
\draw[cp line] ({o})--({p});
\draw[thin,gray] (0,-.25)--(0,{_n(-r*s-.65)});
\draw[thin,gray] ({_n(d*s)},-.25)--({_n(d*s)},{_n(-r*s-.65)});
\draw[<->,thin] (0,{_n(-r*s-.45)})--({_n(d*s)},{_n(-r*s-.45)}) node[midway,below] {{${_label(d,distance[1])}$}};
\draw[cp line] ({o})--({t}) node[midway,left] {{${_label(r,radius[1])}$}};
\draw[cp line] ({t})--({p}) node[midway,above right] {{${lab}$}};
\pic[draw=black,angle radius=3mm] {{right angle={o}--{t}--{p}}};
\node[below left] at ({o}) {{${o}$}};\node[right] at ({p}) {{${p}$}};\node[above] at ({t}) {{${t}$}};''')


def _forces(text):
    if not re.search(r'block',text,re.I) or not re.search(r'four forces',text,re.I):
        return None
    if re.search(r'incline|ramp|angle|friction coefficient|pulley',text,re.I):
        return None
    matches = re.findall(rf'({NUM})\s*(?:N|newtons?)\s+(upward|downward|to the right|to the left)\b',text,re.I)
    # Drawing descriptions often reverse the wording: "the upward arrow 12 N".
    aliases = {'upward':'upward','downward':'downward','rightward':'to the right','leftward':'to the left'}
    matches += [(value,aliases[direction.lower()]) for direction,value in re.findall(
        rf'\b(upward|downward|rightward|leftward)\s+arrow\s*(?:as\s+|with\s+)?({NUM})\s*(?:N|newtons?)\b',text,re.I)]
    forces = {}
    for value, direction in matches:
        direction, value = direction.lower(), float(value)
        if direction in forces and forces[direction] != value:
            return None
        forces[direction] = value
    if set(forces)!={'upward','downward','to the right','to the left'} or any(not 0 < v < 1e6 for v in forces.values()):
        return None
    body = r'\draw[cp line] (-.6,-.4) rectangle (.6,.4);\draw[cp line] (-2,-.4)--(2,-.4);'+'\n'
    for direction,start,delta,anchor in [
        ('upward',(0,.4),(0,1),'above'),('downward',(0,-.4),(0,-1),'below'),
        ('to the right',(.6,0),(1,0),'right'),('to the left',(-.6,0),(-1,0),'left')]:
        length = .65 + .75*forces[direction]/max(forces.values())
        end = (start[0]+delta[0]*length,start[1]+delta[1]*length)
        body += rf'\draw[cp line,->] ({start[0]},{start[1]})--({_n(end[0])},{_n(end[1])}) node[{anchor}] {{${_label(forces[direction],"N")}$}};'+'\n'
    return _result('block_four_forces',forces,body)


def _quadratic(text):
    """Strict polynomial grammar and explicit bounds; never evaluate model text."""
    if not re.search(r'parabola|quadratic|graph|plot', text, re.I):
        return None
    if re.search(r'tangent|normal line|shade|inequality|intersection|parent function|second (?:curve|graph)', text, re.I):
        return None
    # Negative drawing instructions are allowed; positive solved annotations aren't.
    instructions = re.sub(r'do not[^.;]*[.;]?', '', text, flags=re.I)
    if re.search(r'(?:mark|label|dot|highlight)\w*[^.;]*(?:vertex|intercept)', instructions, re.I):
        return None
    cleaned = re.sub(r'\^\{\s*2\s*\}', '^2', text.replace('²', '^2'))
    equations = []
    for match in re.finditer(r'\by\s*=\s*', cleaned):
        rhs = re.match(r'[\d.x+\-*/^{}()\\\s]+', cleaned[match.end():])
        if not rhs:
            return None
        remainder = cleaned[match.end()+rhs.end():]
        next_word = re.match(r'[A-Za-z_]+', remainder)
        if next_word and not rhs[0].rstrip().endswith('.'):
            # Whitespace must not make an unsupported factor look like prose.
            if not rhs[0][-1].isspace() or next_word[0].lower() not in {'is','for','over','on','with','where','and','shown'}:
                return None
        expression = re.sub(r'\s+', '', rhs[0]).rstrip('.')
        decimal = r'(?:\d+(?:\.\d+)?|\.\d+)'
        term = rf'(?:{decimal}\*?)?x(?:\^2)?|{decimal}'
        if not re.fullmatch(rf'[+-]?(?:{term})(?:[+-](?:{term}))*', expression):
            return None
        coefficients = [0.0, 0.0, 0.0]
        powers = set()
        for part in re.findall(r'[+-]?[^+-]+', expression):
            power = 2 if 'x^2' in part else 1 if 'x' in part else 0
            if power in powers:
                return None
            powers.add(power)
            coefficient = part.split('x')[0].rstrip('*') if power else part
            coefficients[power] = float(coefficient+'1' if coefficient in ('', '+', '-') else coefficient)
        if not coefficients[2] or any(not math.isfinite(v) or abs(v) > 10000 for v in coefficients):
            return None
        equations.append(tuple(coefficients))
    if not equations or len(set(equations)) != 1:
        return None
    cleaned = cleaned.replace(r'\leq', '<=').replace(r'\le', '<=').replace('≤', '<=')
    domains = re.findall(rf'({NUM})\s*<=\s*x\s*<=\s*({NUM})', cleaned)
    domains += re.findall(rf'(?:domain|x\s*[- ]\s*axis)\s+(?:from\s+)?({NUM})\s*to\s*({NUM})', cleaned, re.I)
    domains += re.findall(rf'domain\s*\[\s*({NUM})\s*,\s*({NUM})\s*\]', cleaned, re.I)
    ranges = re.findall(rf'y\s*[- ]\s*axis\s+from\s*({NUM})\s*to\s*({NUM})', cleaned, re.I)
    xbounds = {(float(lo),float(hi)) for lo,hi in domains}
    ybounds = {(float(lo),float(hi)) for lo,hi in ranges}
    if len(xbounds) != 1 or len(ybounds) != 1:
        return None
    xmin,xmax = next(iter(xbounds))
    ymin,ymax = next(iter(ybounds))
    if any(not lo < hi or hi-lo > 40 or max(abs(lo),abs(hi)) > 1000 for lo,hi in [(xmin,xmax),(ymin,ymax)]):
        return None
    c,b,a = equations[0]
    return _result('quadratic_explicit_bounds', dict(a=a,b=b,c=c,domain=[xmin,xmax],yrange=[ymin,ymax]), rf'''
\begin{{axis}}[width=7cm,height=7cm,axis lines=middle,xlabel=$x$,ylabel=$y$,
xmin={_n(xmin)},xmax={_n(xmax)},ymin={_n(ymin)},ymax={_n(ymax)},xtick distance=1,ytick distance=1,
tick label style={{font=\small}},grid=major,grid style={{gray!25,thin}},clip=true,clip mode=individual]
\addplot[cp line,no marks,samples=161,domain={_n(xmin)}:{_n(xmax)}] {{{_n(a)}*x^2+({_n(b)})*x+({_n(c)})}};
\end{{axis}}''')


def generate(text):
    """Return an exact supported numerical setup, otherwise leave custom generation intact."""
    text = text.replace('\u2212', '-').replace('\u2013', '-')
    for parser in (_triangle, _points, _tangent, _forces, _quadratic):
        hit = parser(text)
        if hit:
            return hit
    return None
