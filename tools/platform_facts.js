window.__btkPlatformFacts = (action) => {
  const de = document.documentElement, vv = window.visualViewport, s = screen;
  const mq = q => matchMedia(q).matches;
  // Shadow DOM isolates the measuring element from application styles (including !important).
  const host = document.createElement('btk-facts-probe');
  for (const [key,value] of Object.entries({all:'initial',position:'fixed',left:'-10000px',top:'0',
      visibility:'hidden','pointer-events':'none',display:'block',width:'0',height:'0',border:'0',margin:'0',padding:'0'}))
    host.style.setProperty(key,value,'important');
  const probe = document.createElement('div');
  probe.style.cssText = 'all:initial;display:block;box-sizing:content-box;border:0;margin:0;width:100px;height:100px;overflow:scroll;padding:env(safe-area-inset-top,0px) env(safe-area-inset-right,0px) env(safe-area-inset-bottom,0px) env(safe-area-inset-left,0px)';
  host.attachShadow({mode:'closed'}).append(probe);
  document.body.append(host);
  const safe = getComputedStyle(probe);
  const insets = {top: safe.paddingTop, right: safe.paddingRight, bottom: safe.paddingBottom, left: safe.paddingLeft};
  const classic = probe.offsetWidth - probe.clientWidth;
  host.remove();
  const ctx = document.createElement('canvas').getContext('2d');
  const width = font => { ctx.font = font; return +ctx.measureText('Hamburgefonstiv 日本語 0123').width.toFixed(2); };
  // A font that is not installed falls back to the generic family that follows it, so Meiryo is
  // rendering only when "Meiryo, monospace" and "Meiryo, serif" measure the same. null: the two
  // fallbacks themselves measure the same here, so the question cannot be answered.
  const meiryo = () => {
    const mono = width('16px "Meiryo", monospace'), serif = width('16px "Meiryo", serif');
    return width('16px monospace') === width('16px serif') ? null : mono === serif;
  };
  // What the page asks for, not what the OS has: the declared stack of the document body.
  const bodyFamily = getComputedStyle(document.body).fontFamily.slice(0, 200);
  const r = action.getBoundingClientRect();
  return {
    screen: { width: s.width, height: s.height, avail_width: s.availWidth, avail_height: s.availHeight,
              avail_left: s.availLeft ?? null, avail_top: s.availTop ?? null, color_depth: s.colorDepth },
    window: { outer_width: outerWidth, outer_height: outerHeight, inner_width: innerWidth, inner_height: innerHeight,
              screen_x: screenX, screen_y: screenY,
              frame_width: outerWidth - innerWidth, frame_height: outerHeight - innerHeight },
    viewport: { client_width: de.clientWidth, client_height: de.clientHeight,
                scrollbar_width: innerWidth - de.clientWidth,
                // Classic scrollbars take width; overlay scrollbars (macOS default, mobile) take none.
                scrollbar_classic: classic,
                visual_width: vv ? +vv.width.toFixed(2) : null, visual_height: vv ? +vv.height.toFixed(2) : null,
                visual_scale: vv ? vv.scale : null, device_pixel_ratio: devicePixelRatio },
    safe_area: insets,
    input: { pointer_fine: mq('(pointer: fine)'), pointer_coarse: mq('(pointer: coarse)'), hover: mq('(hover: hover)'),
             max_touch_points: navigator.maxTouchPoints },
    preference: { dark: mq('(prefers-color-scheme: dark)'), reduced_motion: mq('(prefers-reduced-motion: reduce)') },
    fonts: { sans: width('16px sans-serif'), serif: width('16px serif'), mono: width('16px monospace'),
             system_ui: width('16px system-ui'), meiryo: meiryo(), body_family: bodyFamily },
    action_box: { x: +r.x.toFixed(2), y: +r.y.toFixed(2), width: +r.width.toFixed(2), height: +r.height.toFixed(2) },
    platform: { ua: navigator.userAgent, platform: navigator.userAgentData?.platform || navigator.platform,
                mobile: navigator.userAgentData?.mobile ?? null, language: navigator.language },
  };
};
