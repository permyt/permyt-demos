document.addEventListener("DOMContentLoaded", function () {
  var ease = "cubic-bezier(0.16, 1, 0.3, 1)";

  // ── Smooth scroll for .scroll-to links ──────────────────────────
  document.querySelectorAll(".scroll-to").forEach(function (link) {
    link.addEventListener("click", function (e) {
      var href = this.getAttribute("href");
      if (href && href.startsWith("#")) {
        e.preventDefault();
        var target = document.querySelector(href);
        if (target) {
          target.scrollIntoView({ behavior: "smooth" });
          // Close mobile nav
          var navLinks = document.querySelector(".nav-links");
          if (navLinks) navLinks.classList.remove("open");
        }
      }
    });
  });

  // ── Staggered fade-in with IntersectionObserver ─────────────────
  // Groups sibling .fade-in elements and triggers them together
  // with cascade delays via --stagger CSS custom property
  var fadeEls = document.querySelectorAll(".fade-in");
  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    fadeEls.forEach(function (el) {
      observer.observe(el);
    });
  } else {
    fadeEls.forEach(function (el) {
      el.classList.add("visible");
    });
  }

  // ── Navbar scroll state ─────────────────────────────────────────
  // Adds .scrolled class for backdrop blur + compact padding
  var navbar = document.querySelector(".navbar");
  if (navbar) {
    var scrollThreshold = 40;
    var ticking = false;

    function updateNavbar() {
      if (window.scrollY > scrollThreshold) {
        navbar.classList.add("scrolled");
      } else {
        navbar.classList.remove("scrolled");
      }
      ticking = false;
    }

    window.addEventListener("scroll", function () {
      if (!ticking) {
        requestAnimationFrame(updateNavbar);
        ticking = true;
      }
    }, { passive: true });

    // Run once on load
    updateNavbar();
  }

  // ── Mobile nav toggle ──────────────────────────────────────────
  var navToggle = document.querySelector(".nav-toggle");
  var navLinks = document.querySelector(".nav-links");
  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      navLinks.classList.toggle("open");
    });
  }
});
