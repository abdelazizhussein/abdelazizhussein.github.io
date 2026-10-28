/* Old-school faculty-page look with a toggle to the modern design.
   Retro is the default. The choice is remembered per browser, and
   ?style=modern or ?style=retro in the URL overrides it. */
(function () {
	var KEY = "site-style";
	// The local site editors preview pages in an about:srcdoc frame; keep those modern.
	var preview = location.href === "about:srcdoc";
	var mode = preview ? "modern" : "retro";
	if (!preview) { try { mode = localStorage.getItem(KEY) || "retro"; } catch (e) {} }
	var m = location.search.match(/[?&]style=(retro|modern)/);
	if (m) { mode = m[1]; save(mode); }

	function save(v) { try { localStorage.setItem(KEY, v); } catch (e) {} }

	// The theme's stylesheet and the pages' own <style> blocks are switched off
	// in retro mode; KaTeX's math styles always stay on.
	function apply() {
		var retro = mode === "retro";
		document.documentElement.classList.toggle("retro", retro);
		var sheets = document.querySelectorAll('link[rel="stylesheet"], style');
		for (var i = 0; i < sheets.length; i++) {
			var s = sheets[i];
			if (s.id === "retro-css") s.media = retro ? "all" : "not all";
			else if (s.tagName === "STYLE" || /assets\/css\/main\.css/.test(s.getAttribute("href") || ""))
				s.media = retro ? "not all" : "all";
		}
		// Old pages had no collapsible sections: open every <details> in retro
		// mode and restore each one's previous state when going back to modern.
		var details = document.querySelectorAll("details");
		for (var k = 0; k < details.length; k++) {
			var dt = details[k];
			if (retro) {
				if (dt.dataset.wasOpen === undefined) dt.dataset.wasOpen = dt.open ? "1" : "";
				dt.open = true;
			} else if (dt.dataset.wasOpen !== undefined) {
				dt.open = dt.dataset.wasOpen === "1";
				delete dt.dataset.wasOpen;
			}
		}
		var extras = document.querySelectorAll(".retro-only");
		for (var j = 0; j < extras.length; j++) extras[j].style.display = retro ? "" : "none";
		var btn = document.getElementById("style-toggle");
		if (btn) styleButton(btn, retro);
	}

	function styleButton(btn, retro) {
		btn.textContent = retro ? "Back to grad student mode ✨" : "What if I were faculty?";
		btn.style.cssText = "position:fixed;right:10px;z-index:10000;cursor:pointer;" + (retro ? "bottom:10px;" : "top:10px;") + (retro
			? "font:16px 'Times New Roman',serif;padding:4px 10px;"
			: "font:600 12px/1 'Source Sans Pro',Helvetica,sans-serif;letter-spacing:.04em;padding:.6em 1em;" +
			  "height:auto;line-height:1;border-radius:999px;border:1px solid #ccc;background:rgba(255,255,255,.92);" +
			  "color:#444;box-shadow:0 2px 8px rgba(0,0,0,.12);text-transform:none;");
	}

	function addExtras() {
		var name = document.querySelector("#header h1");
		if (name) {
			var card = document.createElement("p");
			card.className = "retro-only retro-card";
			card.innerHTML = "Physics PhD Student<br>" +
				"<a href=\"https://physics.mit.edu/\">Department of Physics</a>, Massachusetts Institute of Technology<br>" +
				"<a href=\"https://space.mit.edu/\">MIT Kavli Institute for Astrophysics and Space Research</a><br>" +
				"E-mail: <a href=\"mailto:abdelh@mit.edu\">abdelh@mit.edu</a>";
			name.parentNode.insertBefore(card, name.nextSibling);
		}
		var foot = document.createElement("div");
		foot.id = "retro-footer";
		foot.className = "retro-only";
		var orig = document.querySelector("#footer .inner");
		if (orig) foot.innerHTML = orig.innerHTML;
		document.body.appendChild(foot);
		var d = new Date(document.lastModified);
		var when = isNaN(d) ? "" : d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
		var f = document.createElement("div");
		f.className = "retro-only retro-foot";
		f.innerHTML = (when ? "Last modified: " + when + "<br>" : "") +
			"Best viewed with Netscape Navigator 4.0 at 800&times;600.";
		foot.appendChild(f);

		document.addEventListener("click", function (e) {
			if (mode === "retro" && e.target.closest && e.target.closest("summary") && !e.target.closest("a")) e.preventDefault();
		});

		var btn = document.createElement("button");
		btn.id = "style-toggle";
		btn.type = "button";
		btn.addEventListener("click", function () {
			mode = mode === "retro" ? "modern" : "retro";
			save(mode);
			apply();
			window.scrollTo(0, 0);
		});
		document.body.appendChild(btn);
		apply();
	}

	apply();
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addExtras);
	else addExtras();
})();
