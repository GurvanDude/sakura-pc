// Pétales de sakura sur <canvas> : chute douce, rafales, explosions et "danse" (mode musique).
(function () {
  const TAU = Math.PI * 2;

  function makeSprite(color, edge, glow) {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g = c.getContext('2d');
    g.translate(32, 34);
    if (glow) { g.shadowColor = glow; g.shadowBlur = 10; }
    // pétale avec l'encoche caractéristique au bout
    g.beginPath();
    g.moveTo(0, 20);
    g.bezierCurveTo(-18, 8, -16, -16, -5, -20);
    g.lineTo(0, -14);
    g.lineTo(5, -20);
    g.bezierCurveTo(16, -16, 18, 8, 0, 20);
    const grad = g.createLinearGradient(0, -20, 0, 20);
    grad.addColorStop(0, edge); grad.addColorStop(1, color);
    g.fillStyle = grad;
    g.fill();
    g.shadowBlur = 0;
    g.strokeStyle = 'rgba(255,255,255,.35)';
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(0, 16); g.lineTo(0, -8); g.stroke();
    return c;
  }

  class Petals {
    constructor(canvas, theme) {
      this.cv = canvas; this.ctx = canvas.getContext('2d');
      this.items = []; this.mode = 'fall'; this.t = 0; this.wind = 0;
      // chute d'ambiance : proportion active (0..1) et bord gauche de la zone où elle peut apparaître
      this.ambient = 1; this.minX = 0;
      this.setTheme(theme);
      this.resize(); addEventListener('resize', () => this.resize());
      this.last = performance.now();
      requestAnimationFrame(this.loop.bind(this));
    }
    setTheme(theme) {
      const night = theme === 'night';
      this.sprites = night
        ? [makeSprite('#ff9fcb', '#ffd6ea', 'rgba(255,90,170,.9)'), makeSprite('#ff7fb8', '#ffc4e0', 'rgba(255,90,170,.9)'), makeSprite('#ffc1de', '#ffffff', 'rgba(255,150,210,.8)')]
        : [makeSprite('#f9b4c8', '#ffe8ef'), makeSprite('#f7a1bb', '#ffdbe6'), makeSprite('#ffd0dc', '#ffffff')];
      this.count = night ? 46 : 56;
    }
    resize() {
      this.w = this.cv.width = innerWidth;
      this.h = this.cv.height = innerHeight;
      this.unit = this.h / 900;
    }
    spawn(anywhere) {
      const depth = Math.random();
      return {
        x: Math.random() * this.w * 1.2 - this.w * .1,
        y: anywhere ? Math.random() * this.h : -40 - Math.random() * 200,
        vx: 0, vy: 0,
        size: (10 + depth * 18),
        depth,
        rot: Math.random() * TAU, vr: (Math.random() - .5) * 1.6,
        flip: Math.random() * TAU, vf: 1 + Math.random() * 2.5,
        sway: Math.random() * TAU, swayAmp: 20 + Math.random() * 40,
        fall: 28 + depth * 46,
        sprite: (Math.random() * this.sprites.length) | 0,
        life: Infinity, alpha: .55 + depth * .45, fade: 1,
      };
    }
    burst(x, y, n = 18, power = 1) {
      for (let i = 0; i < n; i++) {
        const p = this.spawn(false);
        const a = Math.random() * TAU, s = (120 + Math.random() * 360) * power;
        Object.assign(p, { x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s - 120 * power, life: 2.2 + Math.random() * 1.5, vr: (Math.random() - .5) * 8 });
        this.items.push(p);
      }
    }
    // un pétale lancé à une vitesse donnée (tempête d'ouverture)
    fling(x, y, vx, vy, life) {
      const p = this.spawn(false);
      Object.assign(p, { x, y, vx, vy, life, vr: (Math.random() - .5) * 9 });
      this.items.push(p);
    }
    setMode(m) { this.mode = m; }
    // rafale qui balaie l'écran de gauche à droite (fermeture de l'appli)
    gust(dur = 1.6, n = 140) {
      this.mode = 'fall';
      this.gustUntil = this.t + dur;
      for (let i = 0; i < n; i++) {
        const p = this.spawn(false);
        Object.assign(p, { x: -60 - Math.random() * this.w * .6, y: Math.random() * this.h, vx: 900 + Math.random() * 900, vy: (Math.random() - .5) * 200, life: 2.6, vr: (Math.random() - .5) * 10 });
        this.items.push(p);
      }
    }
    loop(now) {
      const dt = Math.min(.05, (now - this.last) / 1000); this.last = now; this.t += dt;
      const { ctx, w, h, unit } = this;
      ctx.clearRect(0, 0, w, h);
      // vent : lent + rafales occasionnelles
      const gust = Math.max(0, Math.sin(this.t * .23) * Math.sin(this.t * .71 + 1)) ** 3;
      this.wind = 18 + 120 * gust + (this.t < (this.gustUntil || 0) ? 900 : 0);
      const cx = w / 2, cy = h * .45;
      // la chute d'ambiance s'installe progressivement, seulement dans la zone déjà révélée
      const target = Math.round(this.count * this.ambient);
      let amb = 0;
      for (const p of this.items) if (p.life === Infinity) amb++;
      for (let k = 0; k < 2 && amb < target; k++, amb++) {
        const p = this.spawn(true);
        p.x = this.minX + Math.random() * (w - this.minX); p.fade = 0;
        this.items.push(p);
      }

      for (let i = this.items.length - 1; i >= 0; i--) {
        const p = this.items[i];
        p.sway += dt * 1.3; p.flip += dt * p.vf; p.rot += dt * p.vr;
        if (this.mode === 'dance') {
          // spirale autour du centre, qui pulse
          const dx = p.x - cx, dy = p.y - cy, d = Math.hypot(dx, dy) || 1;
          const target = h * (.18 + .22 * p.depth) * (1 + .12 * Math.sin(this.t * 6));
          p.vx += (-dy / d * 260 + dx / d * (target - d) * 2.2 - p.vx) * dt * 2;
          p.vy += (dx / d * 260 + dy / d * (target - d) * 2.2 - p.vy) * dt * 2;
          p.x += p.vx * dt; p.y += p.vy * dt;
        } else if (p.life !== Infinity) {
          p.vx *= 1 - dt * 1.4; p.vy = p.vy * (1 - dt * 1.4) + 160 * dt;
          p.x += (p.vx + this.wind * .5) * dt; p.y += p.vy * dt;
          p.life -= dt;
        } else {
          p.x += (this.wind * (.4 + p.depth) + Math.cos(p.sway) * p.swayAmp) * dt * unit;
          p.y += p.fall * dt * unit * (1 + gust * .3);
        }
        if (p.life <= 0 || p.y > h + 60 || p.x > w + 80 || p.x < -120) {
          if (p.life !== Infinity || amb > target) { this.items.splice(i, 1); if (p.life === Infinity) amb--; continue; }
          Object.assign(p, this.spawn(false));
          if (Math.random() < .35) { p.x = -40; p.y = Math.random() * h * .6; }
        }
        if (p.fade < 1) p.fade = Math.min(1, p.fade + dt / .9);
        const s = p.size * unit * 1.25;
        const sc = Math.cos(p.flip);
        ctx.save();
        ctx.globalAlpha = p.alpha * p.fade * (p.life < 1 ? Math.max(0, p.life) : 1);
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.scale(1, .35 + .65 * Math.abs(sc));
        ctx.drawImage(this.sprites[p.sprite], -s / 2, -s / 2, s, s);
        ctx.restore();
      }
      requestAnimationFrame(this.loop.bind(this));
    }
  }
  window.Petals = Petals;
})();
