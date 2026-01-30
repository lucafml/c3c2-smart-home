
// Kleine DOM-Helper, damit ich nicht ständig document.querySelector tippen muss.
function $(sel){ return document.querySelector(sel); }
function $all(sel){ return Array.from(document.querySelectorAll(sel)); }

function showModal(id){
  // Öffnet ein Modal + sperrt Scrollen
  const backdrop = $("#modal-backdrop");
  const modal = document.getElementById(id);
  if(!backdrop || !modal) return;
  backdrop.hidden = false;
  modal.hidden = false;
  modal.setAttribute("aria-hidden","false");
  document.body.style.overflow = "hidden";
  modal.dataset.open = "true";
  const first = modal.querySelector("input, select, button");
  if(first) first.focus();
}

function hideModal(id){
  // Modal schließen und Backdrop ggf. ausblenden
  const backdrop = $("#modal-backdrop");
  const modal = document.getElementById(id);
  if(!backdrop || !modal) return;
  modal.hidden = true;
  modal.setAttribute("aria-hidden","true");
  modal.dataset.open = "false";
  // Close backdrop only if no modals are open
  const anyOpen = $all(".modal").some(m => m.dataset.open === "true");
  if(!anyOpen) backdrop.hidden = true;
  document.body.style.overflow = "";
}

function dismissToast(btn){
  // Toast ausfaden und entfernen
  const toast = btn.closest(".toast");
  if(!toast) return;
  toast.style.transition = "opacity .2s ease, transform .2s ease";
  toast.style.opacity = "0";
  toast.style.transform = "translateY(-6px)";
  setTimeout(()=> toast.remove(), 220);
}

window.dismissToast = dismissToast;
window.showModal = showModal;
window.hideModal = hideModal;

document.addEventListener("click", (e)=>{
  // Klick auf Backdrop schließt offene Modals
  const backdrop = $("#modal-backdrop");
  if(backdrop && e.target === backdrop){
    $all(".modal").forEach(m => { if(m.dataset.open === "true") hideModal(m.id); });
  }
});

document.addEventListener("keydown", (e)=>{
  // ESC schließt das erste offene Modal
  if(e.key === "Escape"){
    const open = $all(".modal").find(m => m.dataset.open === "true");
    if(open) hideModal(open.id);
  }
});

// Auto-dismiss toasts after a bit
window.addEventListener("load", ()=>{
  // Toasts automatisch ausblenden (nach 4,5s)
  const stack = $("#toast-stack");
  if(!stack) return;
  setTimeout(()=> {
    $all("#toast-stack .toast").forEach(t => {
      t.style.transition = "opacity .4s ease, transform .4s ease";
      t.style.opacity = "0";
      t.style.transform = "translateY(-8px)";
      setTimeout(()=> t.remove(), 420);
    });
  }, 4500);
});

// Simple client-side filter for device cards
function bindDeviceFilter(){
  // Live-Filter für Device Cards
  const input = $("#device-filter");
  if(!input) return;
  input.addEventListener("input", ()=>{
    const q = input.value.trim().toLowerCase();
    $all("[data-device-card]").forEach(card=>{
      const hay = (card.dataset.search || "").toLowerCase();
      card.style.display = hay.includes(q) ? "" : "none";
    });
  });
}
window.addEventListener("load", bindDeviceFilter);

// Remove device/button with confirm
function confirmRemove(url){
  // Sicherheitsabfrage, damit man nicht aus Versehen löscht
  if(confirm("Remove this device?")){
    window.location.href = url;
  }
}
window.confirmRemove = confirmRemove;
