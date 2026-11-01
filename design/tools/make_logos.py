"""Génère le logo Sakura PC et ses variantes par appli (design/logo/*.svg).
Une seule fleur de base, cinq pétales échancrés ; chaque appli l'habille à sa façon."""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'logo'
PETAL = 'M0,-6 C-34,-18 -44,-58 -20,-84 Q-9,-80 0,-69 Q9,-80 20,-84 C44,-58 34,-18 0,-6 Z'   # pointe vers le haut
VIEW = 'viewBox="-100 -100 200 200" xmlns="http://www.w3.org/2000/svg"'


def petals(fill, extra=''):
    return ''.join(f'<path d="{PETAL}" transform="rotate({k * 72})" fill="{fill}" {extra}/>' for k in range(5))


def stamens(color, r=34, dot=4.2):
    out = []
    for k in range(5):
        a = k * 72 + 36
        out.append(f'<g transform="rotate({a})"><line x1="0" y1="-8" x2="0" y2="-{r - 4}" stroke="{color}" '
                   f'stroke-width="2.2" stroke-linecap="round"/><circle cy="-{r}" r="{dot}" fill="{color}"/></g>')
    return ''.join(out)


def svg(defs, body):
    return f'<svg {VIEW}><defs>{defs}</defs>{body}</svg>\n'


NEON_STROKE = "stroke='#ff3fa4' stroke-width='6' stroke-linejoin='round'"

GRAD = '''<radialGradient id="pg" cx="0" cy="0" r="80" gradientUnits="userSpaceOnUse">
<stop offset="0" stop-color="#ff2f86"/><stop offset=".45" stop-color="#ff7cb5"/><stop offset="1" stop-color="#ffd3e6"/></radialGradient>'''

LOGOS = {
    # la fleur de base : Sakura PC
    'sakura-pc': svg(GRAD, petals('url(#pg)') + stamens('#c8165f') + '<circle r="9" fill="#fff4f8"/>'),
    # Launcher : la fleur porte un bouton « lecture »
    'launcher': svg(GRAD, petals('url(#pg)') + '<circle r="24" fill="#fff4f8"/><path d="M-7,-12 L13,0 L-7,12 Z" fill="#e0236f"/>'),
    # Light : fleur néon lumineuse
    'light': svg('''<filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="7" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>''',
                 '<rect x="-100" y="-100" width="200" height="200" rx="44" fill="#140818"/>'
                 '<g filter="url(#glow)">' + petals('none', NEON_STROKE) + '</g>'
                 '<g filter="url(#glow)">' + stamens('#7fd8ff', 30, 4) + '</g><circle r="7" fill="#ffffff"/>'),
    # Optimizer : pétales en jauge, une aiguille au centre
    'optimizer': svg(GRAD, petals('url(#pg)') +
                     '<circle r="30" fill="#fff4f8"/>'
                     '<path d="M-20,8 A21,21 0 1 1 20,8" fill="none" stroke="#ffb3d1" stroke-width="5" stroke-linecap="round"/>'
                     '<path d="M-20,8 A21,21 0 0 1 2,-21" fill="none" stroke="#e0236f" stroke-width="5" stroke-linecap="round"/>'
                     '<line x1="0" y1="0" x2="12" y2="-13" stroke="#5a0f30" stroke-width="4" stroke-linecap="round"/>'
                     '<circle r="4.5" fill="#5a0f30"/>'),
    # AI : fleur « data » : contours, circuits et nœuds
    'ai': svg('',
              '<rect x="-100" y="-100" width="200" height="200" rx="44" fill="#1a0b1f"/>' +
              petals('#ff4fa0', 'fill-opacity=".12" stroke="#ff4fa0" stroke-width="4" stroke-linejoin="round"') +
              ''.join(f'<g transform="rotate({k * 72})"><path d="M0,-14 L0,-40 L-9,-50" fill="none" stroke="#ff9ccb" '
                      f'stroke-width="2.5"/><circle cx="-9" cy="-50" r="4" fill="#ffffff"/><circle cy="-40" r="2.6" fill="#ff9ccb"/></g>'
                      for k in range(5)) +
              '<circle r="11" fill="none" stroke="#ffffff" stroke-width="3"/><circle r="4" fill="#ff4fa0"/>'),
}

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in LOGOS.items():
        (OUT / f'{name}.svg').write_text(data, encoding='utf-8')
    print('logos :', ', '.join(LOGOS))
