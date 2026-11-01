// Effets sonores synthétisés (aucun fichier audio) : tintements cristallins, souffle, petit beat.
(function () {
  let ac = null, master = null, verb = null;
  // gamme pentatonique majeure à partir de do
  const PENTA = [0, 2, 4, 7, 9];
  const note = (deg, oct = 0) => 523.25 * 2 ** ((PENTA[((deg % 5) + 5) % 5] + 12 * (oct + Math.floor(deg / 5))) / 12);

  function ctx() {
    if (ac) return ac;
    ac = new (window.AudioContext || window.webkitAudioContext)();
    master = ac.createGain(); master.gain.value = .6;
    verb = ac.createConvolver();
    const len = ac.sampleRate * 2.8, ir = ac.createBuffer(2, len, ac.sampleRate);
    for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 3.5; }
    verb.buffer = ir;
    const wet = ac.createGain(); wet.gain.value = .45;
    verb.connect(wet).connect(master);
    master.connect(ac.destination);
    return ac;
  }
  function bus(gain, dry = 1) {
    const g = ac.createGain(); g.gain.value = gain;
    const d = ac.createGain(); d.gain.value = dry;
    g.connect(d).connect(master); g.connect(verb);
    return g;
  }

  // note cristalline : fondamentale + partiels de cloche, attaque très douce
  function glass(freq, when = 0, gain = .06, dur = 1.6) {
    ctx();
    const t = ac.currentTime + when, o = bus(gain);
    [[1, 1], [2.01, .35], [3.98, .12]].forEach(([m, a]) => {
      const osc = ac.createOscillator(), g = ac.createGain();
      osc.type = 'sine'; osc.frequency.value = freq * m;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(a, t + .012);
      g.gain.exponentialRampToValueAtTime(.0001, t + dur / m);
      osc.connect(g).connect(o); osc.start(t); osc.stop(t + dur + .1);
    });
  }

  function noise(dur) {
    const b = ac.createBuffer(1, ac.sampleRate * dur, ac.sampleRate), d = b.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const s = ac.createBufferSource(); s.buffer = b; return s;
  }
  // souffle de vent filtré (montant ou descendant)
  function whoosh(when = 0, dur = 1.2, up = true, gain = .12) {
    ctx();
    const t = ac.currentTime + when, n = noise(dur), f = ac.createBiquadFilter(), g = ac.createGain();
    f.type = 'bandpass'; f.Q.value = 1.2;
    f.frequency.setValueAtTime(up ? 300 : 2400, t); f.frequency.exponentialRampToValueAtTime(up ? 2400 : 300, t + dur);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + dur * .4); g.gain.linearRampToValueAtTime(0, t + dur);
    n.connect(f).connect(g).connect(bus(1, .8)); n.start(t); n.stop(t + dur);
  }
  function boom(when = 0, gain = .35) {
    ctx();
    const t = ac.currentTime + when, o = ac.createOscillator(), g = ac.createGain();
    o.frequency.setValueAtTime(110, t); o.frequency.exponentialRampToValueAtTime(42, t + .5);
    g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(.0001, t + 1.4);
    o.connect(g).connect(bus(1, 1)); o.start(t); o.stop(t + 1.5);
  }
  function kick(t, gain = .45) {
    const o = ac.createOscillator(), g = ac.createGain();
    o.frequency.setValueAtTime(150, t); o.frequency.exponentialRampToValueAtTime(45, t + .12);
    g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(.0001, t + .35);
    o.connect(g).connect(master); o.start(t); o.stop(t + .4);
  }
  function hat(t, gain = .05) {
    const n = noise(.06), f = ac.createBiquadFilter(), g = ac.createGain();
    f.type = 'highpass'; f.frequency.value = 7000;
    g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(.0001, t + .05);
    n.connect(f).connect(g).connect(master); n.start(t);
  }
  function pad(freqs, when, dur, gain = .035) {
    const t = ac.currentTime + when, o = bus(gain, .7);
    freqs.forEach(fq => [-4, 4].forEach(cents => {
      const osc = ac.createOscillator(), g = ac.createGain();
      osc.type = 'triangle'; osc.frequency.value = fq; osc.detune.value = cents;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(1, t + dur * .35); g.gain.linearRampToValueAtTime(0, t + dur);
      osc.connect(g).connect(o); osc.start(t); osc.stop(t + dur + .05);
    }));
  }

  function pop(freq, up) {
    ctx();
    const t = ac.currentTime, o = ac.createOscillator(), g = ac.createGain(), lp = ac.createBiquadFilter();
    o.type = 'sine';
    o.frequency.setValueAtTime(up ? freq * .7 : freq, t);
    o.frequency.exponentialRampToValueAtTime(up ? freq : freq * .6, t + .07);
    lp.type = 'lowpass'; lp.frequency.value = 2200;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.16, t + .006); g.gain.exponentialRampToValueAtTime(.0001, t + .16);
    o.connect(lp).connect(g).connect(master);
    o.start(t); o.stop(t + .2);
  }

  let lastHover = 0;
  const Sfx = {
    unlock() { ctx(); if (ac.state === 'suspended') ac.resume(); },
    hover() {
      const now = performance.now(); if (now - lastHover < 70) return; lastHover = now;
      glass(note(3, 2), 0, .012, .35);
    },
    select(i = 0) { glass(note(i % 7, 1), 0, .07); glass(note((i % 7) + 2, 1), .06, .045); },
    deselect() { glass(note(1, 0), 0, .05, .9); },
    // applis : petit « pop » doux et sec, sans résonance, qui monte d'un cran à chaque rang
    pick(i = 1) { pop(700 * 2 ** (Math.min(i, 6) / 12), true); },
    unpick() { pop(520, false); },
    // dure toute la tempête (~5 s) : souffle long, nappe qui gonfle, clochettes qui accompagnent le front
    intro() {
      whoosh(0, 5.6, true, .08);
      pad([261.6, 329.6, 392, 493.9], .2, 6.2, .02);
      [0, 2, 4, 2, 5, 7, 4, 9, 7, 10, 9, 12].forEach((d, i) => glass(note(d, 1), .5 + i * .38, .024, 2.6));
      glass(note(0, 2), 5.2, .04, 3.5); glass(note(4, 1), 5.25, .03, 3.5);
    },
    // message de bienvenue : quelques tintements qui montent, très doux
    welcome() { [0, 2, 4, 7, 9].forEach((d, i) => glass(note(d, 1), .2 + i * .22, .03, 2.8)); pad([261.6, 329.6, 392], .1, 3.2, .015); },
    musicLoop() { this.stopMusic(); this.music(); this._music = setInterval(() => this.music(), 5000); },
    stopMusic() { clearInterval(this._music); },
    step() { glass(note(4, 1), 0, .03, .8); },
    go() {
      whoosh(0, 1.1, true, .1);
      [0, 1, 2, 3, 4, 5, 6, 7].forEach(d => glass(note(d, 0), .05 + d * .055, .05, 2.2));
      boom(.5);
    },
    exit() {
      whoosh(0, 1.6, false, .14);
      [7, 5, 4, 2, 0].forEach((d, i) => glass(note(d, 1), .2 + i * .09, .04, 2.5));
    },
    classic() { glass(note(4, 0), 0, .06); glass(note(2, 0), .14, .06); glass(note(0, 0), .28, .07, 2); },
    // mode musique : petit beat 120 bpm avec arpège et nappe
    music() {
      ctx();
      const t0 = ac.currentTime + .05, beat = .5;
      const chords = [[261.6, 329.6, 392], [220, 261.6, 329.6], [174.6, 220, 261.6], [196, 246.9, 293.7]];
      for (let b = 0; b < 10; b++) {
        kick(t0 + b * beat);
        hat(t0 + b * beat + beat / 2);
        if (b % 2) hat(t0 + b * beat + beat * .75, .03);
      }
      chords.forEach((c, i) => pad(c, .05 + i * 1.25, 1.4));
      const arp = [0, 2, 4, 7, 4, 2, 5, 7, 9, 7, 5, 4, 2, 4, 7, 9, 10, 9, 7, 5];
      arp.forEach((d, i) => glass(note(d, 0), .05 + i * .25, .045, .9));
      boom(5.1, .3);
    },
    // nappe d'ambiance (bouton ♪)
    ambient(on) {
      ctx(); clearTimeout(this._amb);
      if (!on) return;
      const chords = [[261.6, 329.6, 392, 493.9], [220, 261.6, 329.6, 392], [174.6, 220, 261.6, 329.6], [196, 246.9, 293.7, 392]];
      let i = 0;
      const loop = () => {
        pad(chords[i++ % 4], 0, 8.5, .022);
        for (let k = 0; k < 3; k++) if (Math.random() < .7) glass(note((Math.random() * 8) | 0, 1), 1 + Math.random() * 6, .018, 2.5);
        this._amb = setTimeout(loop, 8000);
      };
      loop();
    },
  };
  window.Sfx = Sfx;
})();
