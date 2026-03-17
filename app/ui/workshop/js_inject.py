"""JavaScript injected into Steam Workshop pages."""

INJECT_JS = r"""
(function() {
    'use strict';
    if (window.__onyx_v === __VERSION__) return;
    window.__onyx_v = __VERSION__;
    const INST = new Set(__INSTALLED_IDS__);

    document.querySelectorAll('[data-onyx]').forEach(e => e.remove());
    document.querySelectorAll('[data-onyx-p]').forEach(e => e.removeAttribute('data-onyx-p'));

    const dm = window.location.href.match(/filedetails\/?\?.*id=(\d+)/);
    if (dm) {
        const mid = dm[1], have = INST.has(mid);
        const old = document.getElementById('onyx-bar');
        if (old) old.remove();
        const bar = document.createElement('div');
        bar.id = 'onyx-bar'; bar.setAttribute('data-onyx','1');
        Object.assign(bar.style, {position:'fixed',top:'0',left:'0',right:'0',height:'38px',
            background:'linear-gradient(90deg,#0d0d1a,#161628)',color:'#e0e0e0',display:'flex',
            alignItems:'center',justifyContent:'center',zIndex:'999999',
            fontFamily:'"Segoe UI",sans-serif',fontSize:'13px',gap:'12px',
            boxShadow:'0 2px 10px rgba(0,0,0,0.5)'});
        const logo = document.createElement('span');
        Object.assign(logo.style,{fontWeight:'800',color:'#7c8aff',fontSize:'13px'});
        logo.textContent='\u25C6 Onyx'; bar.appendChild(logo);
        const sep = document.createElement('span');
        sep.style.color='#333'; sep.textContent='|'; bar.appendChild(sep);
        if (have) {
            const b = document.createElement('span');
            Object.assign(b.style,{background:'#1b5e20',color:'#81c784',padding:'4px 14px',
                borderRadius:'4px',fontWeight:'700',fontSize:'12px'});
            b.textContent='\u2714 Installed'; bar.appendChild(b);
        } else {
            const b = document.createElement('button');
            Object.assign(b.style,{background:'#388e3c',color:'#fff',padding:'5px 18px',
                borderRadius:'4px',border:'none',fontWeight:'700',fontSize:'12px',cursor:'pointer'});
            b.textContent='\uFF0B Download with Onyx';
            b.onclick=function(e){e.preventDefault();window.location.href='onyx://download/'+mid;};
            bar.appendChild(b);
        }
        document.body.style.paddingTop='38px';
        document.body.insertBefore(bar,document.body.firstChild);
    }

    function addButtons() {
        document.querySelectorAll('a[href*="filedetails"][href*="id="]:not([data-onyx-p])').forEach(function(lk) {
            lk.setAttribute('data-onyx-p','1');
            const m = lk.href.match(/[?&]id=(\d+)/);
            if (!m) return;
            const mid=m[1], have=INST.has(mid);
            let ct = lk.closest('.workshopItem')||lk.closest('.workshopItemPreviewHolder')||lk.parentElement;
            if (!ct||ct.querySelector('[data-onyx]')) return;
            const w = document.createElement('div');
            w.setAttribute('data-onyx','1');
            Object.assign(w.style,{position:'absolute',top:'3px',right:'3px',zIndex:'100',pointerEvents:'auto'});
            if (have) {
                w.innerHTML='<span style="background:rgba(27,94,32,0.9);color:#81c784;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700">\u2714</span>';
            } else {
                const b=document.createElement('button');
                Object.assign(b.style,{display:'inline-flex',alignItems:'center',justifyContent:'center',
                    width:'24px',height:'24px',background:'rgba(56,142,60,0.9)',color:'#fff',
                    borderRadius:'4px',border:'none',fontSize:'16px',fontWeight:'700',cursor:'pointer',
                    boxShadow:'0 1px 4px rgba(0,0,0,0.4)',lineHeight:'1'});
                b.textContent='+'; b.title='Download with Onyx';
                b.onclick=function(e){e.preventDefault();e.stopPropagation();
                    window.location.href='onyx://download/'+mid;b.textContent='...';b.style.background='#555';};
                w.appendChild(b);
            }
            const cs=window.getComputedStyle(ct);
            if(cs.position==='static') ct.style.position='relative';
            ct.appendChild(w);
        });
    }
    addButtons();
    if (!window.__onyx_obs) {
        let t=null;
        window.__onyx_obs=new MutationObserver(function(){clearTimeout(t);t=setTimeout(addButtons,400);});
        window.__onyx_obs.observe(document.body,{childList:true,subtree:true});
    }
})();
"""