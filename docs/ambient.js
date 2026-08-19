(() => {
  const canvas = document.getElementById('heroSnow');
  const hero = document.querySelector('.hero-banner');
  if (!canvas || !hero || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const context = canvas.getContext('2d');
  const particles = [];
  let width = 0;
  let height = 0;
  let scale = 1;
  let rafId = 0;
  let visible = true;
  let lastTime = performance.now();
  let lastActivity = lastTime;
  let bank = [];

  function random(min, max) {
    return min + Math.random() * (max - min);
  }

  function makeParticle(initial) {
    return {
      x: random(0, width),
      y: initial ? random(0, height) : random(-height * .35, -8),
      radius: random(.8, 2.5),
      speed: random(10, 27),
      drift: random(-10, 10),
      phase: random(0, Math.PI * 2),
    };
  }

  function resize() {
    const rect = hero.getBoundingClientRect();
    scale = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, Math.floor(rect.width));
    height = Math.max(1, Math.floor(rect.height));
    canvas.width = Math.floor(width * scale);
    canvas.height = Math.floor(height * scale);
    context.setTransform(scale, 0, 0, scale, 0, 0);

    const bankPoints = Math.max(28, Math.ceil(width / 22));
    bank = Array.from({ length: bankPoints }, () => 0);
    const count = Math.min(104, Math.max(46, Math.floor(width / 14)));
    particles.length = 0;
    for (let index = 0; index < count; index += 1) particles.push(makeParticle(true));
  }

  function markActivity() {
    lastActivity = performance.now();
  }

  function drawBank(idle, elapsed, idleDuration) {
    if (idle) {
      const targetDepth = Math.min(64, 12 + idleDuration * 8);
      const settleRate = Math.min(1, elapsed * 1.8);
      bank = bank.map((value, index) => {
        const contour = .82 + Math.sin(index * .61) * .10 + Math.sin(index * .19) * .08;
        return value + (targetDepth * contour - value) * settleRate;
      });
    } else {
      const melt = Math.max(0, 1 - elapsed * .55);
      bank = bank.map((value) => value * melt);
    }
    const maxDepth = Math.max(...bank);
    if (maxDepth < .15) return;

    const spacing = width / (bank.length - 1);
    context.beginPath();
    context.moveTo(0, height);
    for (let index = 0; index < bank.length; index += 1) {
      const previous = bank[Math.max(0, index - 1)];
      const next = bank[Math.min(bank.length - 1, index + 1)];
      const smoothDepth = (previous + bank[index] * 2 + next) / 4;
      context.lineTo(index * spacing, height - 4 - smoothDepth);
    }
    context.lineTo(width, height);
    context.closePath();
    context.fillStyle = 'rgba(243, 250, 252, .94)';
    context.fill();
  }

  function frame(time) {
    const elapsed = Math.min((time - lastTime) / 1000, .05);
    lastTime = time;
    const idleDuration = Math.max(0, (time - lastActivity - 3000) / 1000);
    const idle = idleDuration > 0;
    context.clearRect(0, 0, width, height);

    particles.forEach((particle) => {
      particle.phase += elapsed * .9;
      particle.x += (particle.drift + Math.sin(particle.phase) * 7) * elapsed;
      particle.y += particle.speed * elapsed;

      if (particle.y > height - 6) {
        if (idle) {
          const position = Math.max(0, Math.min(bank.length - 1, Math.floor((particle.x / width) * bank.length)));
          bank[position] = Math.min(72, bank[position] + particle.radius * 1.4);
        }
        Object.assign(particle, makeParticle(false));
      } else if (particle.x < -8 || particle.x > width + 8) {
        particle.x = particle.x < 0 ? width + 4 : -4;
      }

      context.beginPath();
      context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
      context.fillStyle = particle.radius > 1.8 ? 'rgba(255,255,255,.78)' : 'rgba(226,244,247,.68)';
      context.fill();
    });

    drawBank(idle, elapsed, idleDuration);
    rafId = visible ? requestAnimationFrame(frame) : 0;
  }

  const observer = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    if (visible && !rafId) {
      lastTime = performance.now();
      rafId = requestAnimationFrame(frame);
    }
    if (!visible && rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
  }, { threshold: 0 });

  resize();
  observer.observe(hero);
  window.addEventListener('resize', resize, { passive: true });
  ['pointermove', 'pointerdown', 'touchstart', 'keydown', 'scroll'].forEach((eventName) => {
    window.addEventListener(eventName, markActivity, { passive: true });
  });
})();
