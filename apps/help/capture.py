"""Минимальный WebDriver-клиент и аннотирование реальных страниц без внешних Python-зависимостей."""
import base64
from dataclasses import dataclass
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request


@dataclass(frozen=True)
class Shot:
    key: str
    user: str
    url: str
    selectors: tuple[str, ...]
    focus: str = 'main'
    height: int = 1100


class WebDriverError(RuntimeError):
    pass


class WebDriver:
    ELEMENT_KEY = 'element-6066-11e4-a52e-4f735466cecf'

    def __init__(self, endpoint, base_url):
        self.endpoint = endpoint.rstrip('/')
        self.base_url = base_url.rstrip('/')
        self.session_id = None

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.endpoint + path, data=data, method=method,
            headers={'Content-Type': 'application/json; charset=utf-8'},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors='replace')
            raise WebDriverError(f'WebDriver {method} {path}: HTTP {exc.code}: {body}') from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WebDriverError(f'WebDriver {method} {path}: {exc}') from exc
        value = result.get('value')
        if isinstance(value, dict) and value.get('error'):
            raise WebDriverError(f'WebDriver {method} {path}: {value}')
        return value

    def start(self):
        value = self.request('POST', '/session', {
            'capabilities': {'alwaysMatch': {
                'browserName': 'firefox',
                'moz:firefoxOptions': {
                    'args': ['-headless'],
                    'prefs': {'browser.cache.disk.enable': False, 'browser.cache.memory.enable': False},
                },
            }},
        })
        self.session_id = value['sessionId']
        self.request('POST', f'/session/{self.session_id}/timeouts', {'implicit': 5000, 'pageLoad': 60000})
        self.rect(1440, 1100)

    def close(self):
        if self.session_id:
            try:
                self.request('DELETE', f'/session/{self.session_id}')
            finally:
                self.session_id = None

    def path(self, suffix):
        if not self.session_id:
            raise WebDriverError('Сессия WebDriver не запущена')
        return f'/session/{self.session_id}{suffix}'

    def rect(self, width, height):
        self.request('POST', self.path('/window/rect'), {'x': 0, 'y': 0, 'width': width, 'height': height})

    def navigate(self, url):
        absolute = url if url.startswith('http') else self.base_url + url
        self.request('POST', self.path('/url'), {'url': absolute})
        for _ in range(100):
            if self.execute('return document.readyState') == 'complete':
                return
            time.sleep(.05)
        raise WebDriverError(f'Страница не загрузилась: {absolute}')

    def execute(self, script, *args):
        return self.request('POST', self.path('/execute/sync'), {'script': script, 'args': list(args)})

    def element(self, selector):
        value = self.request('POST', self.path('/element'), {'using': 'css selector', 'value': selector})
        return value[self.ELEMENT_KEY]

    def type(self, selector, text):
        element = self.element(selector)
        self.request('POST', self.path(f'/element/{element}/value'), {'text': text, 'value': list(text)})

    def click(self, selector):
        element = self.element(selector)
        self.request('POST', self.path(f'/element/{element}/click'), {})

    def login(self, username, password):
        self.navigate('/login/')
        self.type('#id_username', username)
        self.type('#id_password', password)
        self.click('button[type="submit"]')
        for _ in range(100):
            if not self.execute('return location.pathname').startswith('/login'):
                return
            time.sleep(.05)
        raise WebDriverError(f'Не удалось войти под пользователем {username}')

    def capture(self, shot, destination):
        self.navigate(shot.url)
        self.rect(1440, shot.height)
        focus = shot.focus.split('|')
        focused = self.execute(
            'const s=arguments[0]; document.documentElement.style.scrollBehavior="auto"; '
            'for (const q of s) { const e=document.querySelector(q); if (e) { '
            'const y=e.getBoundingClientRect().top+window.scrollY-70; window.scrollTo(0,Math.max(0,y)); return q; } } return null;',
            focus,
        )
        if not focused:
            raise WebDriverError(f'{shot.key}: не найден блок прокрутки {shot.focus}')
        time.sleep(.12)
        script = r'''
const groups=arguments[0];
const old=document.getElementById('help-capture-overlay'); if(old) old.remove();
const overlay=document.createElement('div'); overlay.id='help-capture-overlay';
overlay.style.cssText='position:fixed;inset:0;pointer-events:none;z-index:2147483647';
const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
svg.setAttribute('width',innerWidth); svg.setAttribute('height',innerHeight);
svg.style.cssText='position:absolute;inset:0;overflow:visible';
svg.innerHTML='<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#c2185b"/></marker></defs>';
overlay.appendChild(svg);
const labels=[]; let x1=innerWidth,y1=innerHeight,x2=0,y2=0;
for(let i=0;i<groups.length;i++) {
  let el=null;
  for(const q of groups[i].split('|')) { const candidate=document.querySelector(q); if(candidate) {el=candidate;break;} }
  if(!el) throw new Error('Не найден элемент '+(i+1)+': '+groups[i]);
  const r=el.getBoundingClientRect();
  if(r.width<2 || r.height<2 || r.bottom<0 || r.top>innerHeight) throw new Error('Элемент вне кадра '+(i+1)+': '+groups[i]);
  const left=Math.max(2,r.left-4), top=Math.max(2,r.top-4), right=Math.min(innerWidth-2,r.right+4), bottom=Math.min(innerHeight-2,r.bottom+4);
  const frame=document.createElement('div');
  frame.style.cssText=`position:fixed;left:${left}px;top:${top}px;width:${right-left}px;height:${bottom-top}px;border:3px solid #c2185b;border-radius:5px;box-sizing:border-box;background:rgba(255,255,255,0.025)`;
  overlay.appendChild(frame);
  const bx=Math.min(innerWidth-46,Math.max(8,right+18)), by=Math.min(innerHeight-46,Math.max(8,top-10));
  const tx=Math.max(left,Math.min(right,left+(right-left)*.55)), ty=Math.max(top,Math.min(bottom,top+18));
  const line=document.createElementNS('http://www.w3.org/2000/svg','line');
  line.setAttribute('x1',bx+17);line.setAttribute('y1',by+17);line.setAttribute('x2',tx);line.setAttribute('y2',ty);
  line.setAttribute('stroke','#c2185b');line.setAttribute('stroke-width','3');line.setAttribute('marker-end','url(#arrow)');svg.appendChild(line);
  const badge=document.createElement('div'); badge.textContent=String(i+1);
  badge.style.cssText=`position:fixed;left:${bx}px;top:${by}px;width:36px;height:36px;border-radius:50%;background:#c2185b;color:white;border:3px solid white;box-shadow:0 1px 5px #0006;display:flex;align-items:center;justify-content:center;font:700 20px/1 Arial,sans-serif`;
  overlay.appendChild(badge); labels.push(groups[i]);
  x1=Math.min(x1,left,bx); y1=Math.min(y1,top,by); x2=Math.max(x2,right,bx+36); y2=Math.max(y2,bottom,by+36);
}
document.body.appendChild(overlay);
const x=Math.max(0,Math.floor(x1-45)), y=Math.max(0,Math.floor(y1-100));
const right=Math.min(innerWidth,Math.ceil(x2+45)), bottom=Math.min(innerHeight,Math.ceil(y2+45));
return {labels:labels,crop:{x:x,y:y,width:Math.max(1,right-x),height:Math.max(1,bottom-y)}};
'''
        try:
            annotation = self.execute(script, list(shot.selectors))
        except WebDriverError as exc:
            raise WebDriverError(f'{shot.key} ({shot.url}): {exc}') from exc
        time.sleep(.08)
        value = self.request('GET', self.path('/screenshot'))
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = destination.with_name(f'{destination.stem}.raw.png')
        raw.write_bytes(base64.b64decode(value))
        executable = shutil.which('magick') or shutil.which('convert')
        if not executable:
            raise WebDriverError('Для кадрирования скриншотов нужен ImageMagick (magick или convert)')
        crop = annotation['crop']
        geometry = f'{crop["width"]}x{crop["height"]}+{crop["x"]}+{crop["y"]}'
        try:
            subprocess.run([executable, str(raw), '-crop', geometry, '+repage', str(destination)],
                           check=True, capture_output=True, timeout=30)
        except subprocess.CalledProcessError as exc:
            raise WebDriverError(f'{shot.key}: ошибка ImageMagick: {exc.stderr.decode(errors="replace")}') from exc
        finally:
            raw.unlink(missing_ok=True)
        if destination.stat().st_size < 5000 or destination.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
            raise WebDriverError(f'{shot.key}: браузер вернул некорректный PNG')
