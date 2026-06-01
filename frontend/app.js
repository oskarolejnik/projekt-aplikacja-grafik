const API = "/api";
let STATE = { stanowiska: [], pracownicy: [], wymagania: [], dyspozycje: [], przydzialy: [], wybranyTydzien: "" };

// Słownik profesjonalnych ikon wektorowych SVG
const ICONS = {
  plus: `<svg class="w-4 h-4 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>`,
  trash: `<svg class="w-4 h-4 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>`,
  save: `<svg class="w-4 h-4 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`,
  robot: `<svg class="w-5 h-5 inline-block mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>`,
  clock: `<svg class="w-3 h-3 inline-block mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`,
  pin: `<svg class="w-4 h-4 inline-block text-indigo-500 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>`,
  chevronDown: `<svg class="w-4 h-4 text-slate-400 group-open:rotate-180 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>`
};

const tabTitles = {
  "tab-pracownicy": "Zarządzanie Pracownikami",
  "tab-stanowiska": "Struktura i Stanowiska",
  "tab-wymagania": "Planowanie Zmian (Harmonogram)",
  "tab-dyspozycje": "Import Dyspozycji",
  "tab-grafik": "Interaktywny Grafik Pracy",
  "tab-eksport": "Eksport Danych"
};

document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach(b => {
      b.classList.remove("active", "bg-blue-50", "text-blue-700");
      b.classList.add("text-slate-600");
    });
    document.querySelectorAll("section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active", "bg-blue-50", "text-blue-700");
    btn.classList.remove("text-slate-600");
    document.getElementById("top-header-title").innerText = tabTitles[btn.dataset.tab] || "GrafikPro";
    document.getElementById(btn.dataset.tab).classList.add("active");
    loadTab(btn.dataset.tab);
  });
});

function loadTab(tab) {
  switch (tab) {
    case "tab-pracownicy": renderPracownicy(); break;
    case "tab-stanowiska": renderStanowiska(); break;
    case "tab-wymagania":  renderWymagania();  break;
    case "tab-grafik":     renderGrafik();     break;
  }
}

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(API + path, opts);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

async function loadDicts() {
  STATE.stanowiska = await api("/stanowiska");
  STATE.pracownicy = await api("/pracownicy");
}

function generujOpcjeTygodni() {
  const opcje = []; const dzis = new Date();
  const startSroda = new Date(dzis);
  let przesuniecie = dzis.getDay() - 3;
  if (przesuniecie < 0) przesuniecie += 7;
  startSroda.setDate(dzis.getDate() - przesuniecie);
  for (let i = -2; i <= 5; i++) {
    const sroda = new Date(startSroda); sroda.setDate(startSroda.getDate() + (i * 7));
    const wtorek = new Date(sroda); wtorek.setDate(sroda.getDate() + 6);
    const sStr = sroda.toISOString().slice(0, 10); const wStr = wtorek.toISOString().slice(0, 10);
    const value = `${sStr}|${wStr}`;
    if (!STATE.wybranyTydzien && i === 0) STATE.wybranyTydzien = value;
    opcje.push({ value: value, label: `${sStr.split('-').reverse().join('.')} — ${wStr.split('-').reverse().join('.')}` });
  }
  return opcje;
}

function zbudujDropdownTygodni(idAkapitu, funkcjaZdarzenia) {
  const tygodnie = generujOpcjeTygodni();
  return `<select id="${idAkapitu}" onchange="STATE.wybranyTydzien = this.value; ${funkcjaZdarzenia}();" class="bg-white border border-slate-300 text-slate-700 font-semibold text-sm rounded-xl focus:ring-2 focus:ring-blue-500 outline-none block min-w-[250px] p-2.5 shadow-sm cursor-pointer">${tygodnie.map(t => `<option value="${t.value}" ${STATE.wybranyTydzien === t.value ? "selected" : ""}>${t.label}</option>`).join("")}</select>`;
}

// ══════════════════════════════════════════════════════════════════════════
// STANOWISKA
// ══════════════════════════════════════════════════════════════════════════
async function renderStanowiska() {
  await loadDicts();
  const cont = document.getElementById("stanowiska-content");
  let html = `
    <div class="bg-white border border-slate-200 rounded-2xl shadow-sm p-8 mb-8">
      <h3 class="font-bold text-lg text-slate-800 mb-6">Nowe stanowisko (Kategoria Główna)</h3>
      <div class="flex flex-wrap gap-4 items-center">
        <input id="new-stan-nazwa" placeholder="Np. Sala, Bar..." class="border border-slate-300 rounded-xl px-4 py-2.5 outline-none bg-slate-50 w-64">
        <label class="flex items-center gap-2 cursor-pointer bg-slate-50 px-4 py-2.5 rounded-xl border border-slate-200"><input type="checkbox" id="new-stan-weekend" class="w-4 h-4 text-blue-600 rounded"> <span class="font-medium text-slate-700 text-sm">Tylko weekend</span></label>
        <button onclick="createStanowisko()" class="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-6 rounded-xl shadow-sm">${ICONS.plus} Dodaj Stanowisko</button>
      </div>
    </div>
    
    <div class="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden mb-8">
      <table class="w-full text-left text-sm"><thead class="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-xs"><tr><th class="p-4 font-bold">ID</th><th class="p-4 font-bold">Nazwa</th><th class="p-4 font-bold text-center">Tylko weekend</th><th class="p-4 font-bold">Akcje</th></tr></thead><tbody class="divide-y divide-slate-100">
        ${STATE.stanowiska.map(s => `<tr class="hover:bg-slate-50"><td class="p-4 text-slate-400 font-mono text-xs">#${s.id}</td><td class="p-4"><input id="sn-${s.id}" value="${s.nazwa}" class="border border-slate-200 p-2 rounded-lg w-full max-w-[200px] outline-none bg-white"></td><td class="p-4 text-center"><input type="checkbox" id="sw-${s.id}" ${s.tylko_weekend ? "checked" : ""} class="w-4 h-4 rounded"></td><td class="p-4"><button onclick="updateStanowisko(${s.id})" class="text-blue-600 bg-blue-50 hover:bg-blue-100 py-1.5 px-3 rounded-lg mr-2 font-medium">${ICONS.save} Zapisz</button><button onclick="deleteStanowisko(${s.id})" class="text-red-600 bg-red-50 hover:bg-red-100 py-1.5 px-3 rounded-lg font-medium">${ICONS.trash} Usuń</button></td></tr>`).join("")}
      </tbody></table>
    </div>
    
    <div class="bg-indigo-50/50 border border-indigo-100 rounded-2xl shadow-sm p-8">
      <h3 class="text-xl font-bold text-slate-800 mb-2">Szablony Rewirów / Zmian</h3>
      <p class="text-slate-500 text-sm mb-6">Przypisz gotowe rewiry i godziny wejścia do istniejących stanowisk.</p>
      
      <div class="flex flex-wrap items-end gap-4 mb-8 bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
        <label class="flex flex-col gap-1.5 w-full sm:w-auto"><span class="text-sm font-semibold text-slate-700">Stanowisko:</span><select id="new-pk-stan" class="border border-slate-300 rounded-xl px-4 py-2.5 bg-slate-50 outline-none">${STATE.stanowiska.map(s => `<option value="${s.id}">${s.nazwa}</option>`).join("")}</select></label>
        <label class="flex flex-col gap-1.5 w-full sm:w-auto"><span class="text-sm font-semibold text-slate-700">Nazwa rewiru:</span><input id="new-pk-nazwa" placeholder="Wpisz rewir..." class="border border-slate-300 rounded-xl px-4 py-2.5 bg-slate-50 outline-none"></label>
        <label class="flex flex-col gap-1.5 w-full sm:w-auto"><span class="text-sm font-semibold text-slate-700">Godzina wejścia:</span><input type="time" id="new-pk-od" class="border border-slate-300 rounded-xl px-4 py-2.5 bg-slate-50 outline-none"></label>
        <button onclick="createPodkategoria()" class="bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2.5 px-6 rounded-xl shadow-sm">${ICONS.plus} Dodaj Szablon</button>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        ${STATE.stanowiska.map(s => s.podkategorie && s.podkategorie.length > 0 ? `<div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm"><h4 class="font-extrabold text-indigo-800 border-b border-slate-100 pb-3 mb-4">${ICONS.pin} ${s.nazwa}</h4><div class="space-y-3">${s.podkategorie.map(pk => `<div class="flex justify-between items-center bg-slate-50 p-3 rounded-xl border border-slate-100"><div><div class="text-sm font-bold text-slate-800">${pk.nazwa}</div><div class="text-xs font-mono text-slate-500 mt-0.5">${ICONS.clock} Wejście: ${pk.godz_od ? pk.godz_od.slice(0,5) : 'Dowolnie'}</div></div><button onclick="deletePodkategoria(${pk.id})" class="text-red-500 bg-red-50 px-2 py-1.5 rounded-lg text-xs font-bold border border-red-100">${ICONS.trash}</button></div>`).join("")}</div></div>` : "").join("")}
      </div>
    </div>`;
  cont.innerHTML = html;
}
async function createStanowisko() { const n = document.getElementById("new-stan-nazwa").value.trim(); if (!n) return; try { await api("/stanowiska", "POST", { nazwa: n, tylko_weekend: document.getElementById("new-stan-weekend").checked }); renderStanowiska(); } catch (e) { alert(e.message); } }
async function updateStanowisko(id) { try { await api(`/stanowiska/${id}`, "PUT", { nazwa: document.getElementById(`sn-${id}`).value.trim(), tylko_weekend: document.getElementById(`sw-${id}`).checked }); renderStanowiska(); } catch (e) { alert(e.message); } }
async function deleteStanowisko(id) { if (confirm("Usunąć?")) try { await api(`/stanowiska/${id}`, "DELETE"); renderStanowiska(); } catch (e) { alert(e.message); } }
window.createPodkategoria = async function() { const s = document.getElementById("new-pk-stan").value, n = document.getElementById("new-pk-nazwa").value.trim(), o = document.getElementById("new-pk-od").value; if (!n) return; try { await api(`/stanowiska/${s}/podkategorie`, "POST", { nazwa: n, godz_od: o ? `${o}:00` : null }); renderStanowiska(); } catch (e) { alert(e.message); } };
window.deletePodkategoria = async function(p) { if(confirm("Usunąć?")) try { await api(`/podkategorie/${p}`, "DELETE"); renderStanowiska(); } catch(e) { alert(e.message); } };

// ══════════════════════════════════════════════════════════════════════════
// PRACOWNICY (Nowy Kompaktowy Widok Tabeli z Dropdownem)
// ══════════════════════════════════════════════════════════════════════════
async function renderPracownicy() {
  await loadDicts();
  const cont = document.getElementById("pracownicy-content");

  // Kompaktowy Dropdown dla kwalifikacji (HTML5 details)
  const renderKwalifikacjeDropdown = (pracId, kwalIds, isNew = false) => `
    <details class="group bg-slate-50 rounded-xl border border-slate-200">
      <summary class="cursor-pointer font-medium text-xs px-3 py-2 flex justify-between items-center text-slate-700 list-none outline-none">
        Wybierz kwalifikacje (${kwalIds.length}) ${ICONS.chevronDown}
      </summary>
      <div class="p-3 border-t border-slate-200 grid grid-cols-2 lg:grid-cols-3 gap-2 max-h-40 overflow-y-auto bg-white rounded-b-xl">
        ${STATE.stanowiska.map(s => `<label class="flex items-center gap-2 cursor-pointer p-1.5 hover:bg-slate-100 rounded-lg text-xs font-medium"><input type="checkbox" class="${isNew ? 'new-kwal' : `kwal-${pracId}`} w-3.5 h-3.5 text-blue-600 rounded" value="${s.id}" ${kwalIds.includes(s.id) ? "checked" : ""}><span>${s.nazwa}</span></label>`).join("")}
      </div>
    </details>`;

  cont.innerHTML = `
    <div class="bg-blue-50/50 border-2 border-dashed border-blue-300 rounded-2xl p-5 shadow-sm mb-8">
      <h3 class="text-lg font-extrabold text-blue-800 mb-3 flex items-center gap-2">${ICONS.plus} Dodaj pracownika</h3>
      <div class="flex flex-wrap md:flex-nowrap gap-4 items-start">
        <input id="new-p-imie" class="w-full md:w-48 border border-blue-200 p-2.5 rounded-xl bg-white text-sm outline-none" placeholder="Imię">
        <input id="new-p-nazwisko" class="w-full md:w-48 border border-blue-200 p-2.5 rounded-xl bg-white text-sm outline-none" placeholder="Nazwisko">
        <div class="flex-1 w-full">${renderKwalifikacjeDropdown('new', [], true)}</div>
        <button onclick="createPracownik()" class="w-full md:w-auto bg-blue-600 hover:bg-blue-700 text-white font-bold p-2.5 px-6 rounded-xl shadow-sm whitespace-nowrap">Utwórz konto</button>
      </div>
    </div>

    <div class="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-xs">
          <tr>
            <th class="p-4 font-bold w-1/4">Imię i Nazwisko</th>
            <th class="p-4 font-bold text-center w-24">Status</th>
            <th class="p-4 font-bold">Kwalifikacje (Rozwiń)</th>
            <th class="p-4 font-bold text-right w-48">Akcje</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          ${STATE.pracownicy.map(p => {
            const kwalIds = (p.kwalifikacje || []).map(k => k.id);
            return `<tr class="hover:bg-slate-50/50 transition-colors">
              <td class="p-4">
                <div class="flex flex-col gap-1">
                  <input id="pi-${p.id}" value="${p.imie}" class="font-bold text-base text-slate-900 bg-transparent border-b border-transparent focus:border-blue-400 outline-none w-full">
                  <input id="pn-${p.id}" value="${p.nazwisko}" class="font-medium text-xs text-slate-500 bg-transparent border-b border-transparent focus:border-blue-400 outline-none w-full">
                </div>
              </td>
              <td class="p-4 text-center">
                <input type="checkbox" id="pa-${p.id}" ${p.aktywny ? "checked" : ""} class="w-5 h-5 text-emerald-600 rounded cursor-pointer">
              </td>
              <td class="p-4 align-top">
                ${renderKwalifikacjeDropdown(p.id, kwalIds)}
              </td>
              <td class="p-4 text-right align-top space-x-1">
                <button onclick="updatePracownik(${p.id})" class="text-blue-600 bg-blue-50 hover:bg-blue-100 p-2 rounded-lg font-bold">${ICONS.save} Zapisz</button>
                <button onclick="deletePracownik(${p.id})" class="text-red-600 bg-red-50 hover:bg-red-100 p-2 rounded-lg font-bold">${ICONS.trash}</button>
              </td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>
    </div>`;
}

async function createPracownik() { const i = document.getElementById("new-p-imie").value.trim(), n = document.getElementById("new-p-nazwisko").value.trim(); if (!i || !n) return; try { await api("/pracownicy", "POST", { imie: i, nazwisko: n, aktywny: true, kwalifikacje_ids: [...document.querySelectorAll(".new-kwal:checked")].map(el => +el.value) }); renderPracownicy(); } catch (e) { alert(e.message); } }
async function updatePracownik(id) { try { await api(`/pracownicy/${id}`, "PUT", { imie: document.getElementById(`pi-${id}`).value.trim(), nazwisko: document.getElementById(`pn-${id}`).value.trim(), aktywny: document.getElementById(`pa-${id}`).checked, kwalifikacje_ids: [...document.querySelectorAll(`.kwal-${id}:checked`)].map(el => +el.value) }); alert("Zapisano zmiany."); renderPracownicy(); } catch (e) { alert(e.message); } }
async function deletePracownik(id) { if (confirm("Usunąć pracownika?")) try { await api(`/pracownicy/${id}`, "DELETE"); renderPracownicy(); } catch (e) { alert(e.message); } }

// ══════════════════════════════════════════════════════════════════════════
// WYMAGANIA (Karty Pogrupowane Po Dniach Tygodnia!)
// ══════════════════════════════════════════════════════════════════════════
async function renderWymagania() {
  await loadDicts();
  const cont = document.getElementById("wymagania-content");
  
  cont.innerHTML = `
    <div class="mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div class="bg-white p-2 rounded-2xl border border-slate-200 shadow-sm">${zbudujDropdownTygodni("wym-tydzien-sel", "loadWymagania")}</div>
      <button onclick="document.getElementById('form-wymagania').scrollIntoView({behavior:'smooth'})" class="text-sm font-bold bg-slate-100 px-4 py-2 rounded-xl text-slate-700">${ICONS.plus} Skocz do dodawania</button>
    </div>
    
    <div id="wym-cards-cont" class="mb-8"></div>
    
    <div id="form-wymagania" class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <fieldset class="border border-slate-200 p-6 bg-white rounded-2xl shadow-sm">
        <legend class="text-sm font-bold text-emerald-800 px-3 bg-white ml-2 rounded-lg border border-slate-100 shadow-sm py-1 flex items-center">${ICONS.plus} Zaplanuj Zmianę</legend>
        <div class="space-y-4 mt-3">
          <div class="grid grid-cols-2 gap-4">
            <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-slate-600 uppercase">Data</span><input type="date" id="wym-new-data" value="${new Date().toISOString().slice(0, 10)}" class="border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 outline-none text-sm"></label>
            <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-slate-600 uppercase">Stanowisko</span>
              <select id="wym-new-stan" onchange="updateSubcatDropdown()" class="border border-slate-300 bg-slate-50 rounded-xl px-3 py-2 outline-none text-sm"><option value="">Wybierz...</option>${STATE.stanowiska.map(s => `<option value="${s.id}">${s.nazwa}</option>`).join("")}</select>
            </label>
          </div>
          <div id="subcat-container" class="bg-indigo-50/50 border border-indigo-100 p-3 rounded-xl" style="display:none;">
            <label class="flex flex-col gap-1.5 w-full"><span class="text-xs font-bold text-indigo-800 uppercase flex items-center">${ICONS.pin} Szablon rewiru</span><select id="wym-new-subcat" onchange="applySubcatTemplate()" class="border border-indigo-200 bg-white rounded-lg px-2 py-1.5 text-indigo-900 text-sm outline-none"></select></label>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-slate-600 uppercase">Przyjście</span><input type="time" id="wym-new-od" class="border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 outline-none text-sm"></label>
            <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-slate-600 uppercase">Liczba osób</span><input type="number" id="wym-new-liczba" value="1" min="1" class="border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 outline-none font-bold text-center text-sm"></label>
          </div>
          <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-slate-600 uppercase">Rewir / Strefa</span><input id="wym-new-rewir" placeholder="np. BarR1..." class="border border-slate-300 rounded-xl px-3 py-2 bg-slate-50 outline-none text-sm"></label>
          <button onclick="addWymaganie()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 w-full mt-2 rounded-xl shadow-sm text-sm">Dodaj do planu</button>
        </div>
      </fieldset>

      <fieldset class="border border-blue-100 rounded-2xl p-6 bg-blue-50/30 shadow-sm h-fit">
        <legend class="text-sm font-bold text-blue-800 px-3 bg-blue-50 rounded-lg border border-blue-100 py-1 flex items-center">📋 Kopiowanie (Pn-Pt)</legend>
        <p class="text-xs text-slate-500 mb-4 mt-2">Wybierz wzorcowy dzień i skopiuj go na resztę tygodnia.</p>
        <div class="space-y-4">
          <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-blue-800 uppercase">Źródło (Kopiuj z)</span><input type="date" id="kop-source" value="${new Date().toISOString().slice(0, 10)}" class="border border-blue-200 rounded-xl px-3 py-2 bg-white outline-none text-sm"></label>
          <div class="grid grid-cols-2 gap-4">
            <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-slate-600 uppercase">Od dnia</span><input type="date" id="kop-start" class="border border-slate-300 rounded-xl px-3 py-2 bg-white text-sm"></label>
            <label class="flex flex-col gap-1.5"><span class="text-xs font-bold text-slate-600 uppercase">Do dnia</span><input type="date" id="kop-end" class="border border-slate-300 rounded-xl px-3 py-2 bg-white text-sm"></label>
          </div>
          <button onclick="kopiujWymagania()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl mt-2 text-sm">Duplikuj harmonogram</button>
        </div>
      </fieldset>
    </div>`;
  loadWymagania();
}

window.updateSubcatDropdown = function() {
  const s = STATE.stanowiska.find(x => x.id === +document.getElementById("wym-new-stan").value);
  const cont = document.getElementById("subcat-container"), sel = document.getElementById("wym-new-subcat");
  if (s && s.podkategorie && s.podkategorie.length) {
      sel.innerHTML = `<option value="">-- Wpisz ręcznie --</option>` + s.podkategorie.map(pk => `<option value="${pk.id}">${pk.nazwa} (${pk.godz_od ? pk.godz_od.slice(0,5) : 'Brak'})</option>`).join("");
      cont.style.display = "block";
  } else { sel.innerHTML = ""; cont.style.display = "none"; }
};
window.applySubcatTemplate = function() {
  const s = STATE.stanowiska.find(x => x.id === +document.getElementById("wym-new-stan").value); if(!s) return;
  const pk = s.podkategorie.find(x => x.id === +document.getElementById("wym-new-subcat").value);
  if(pk) { document.getElementById("wym-new-rewir").value = pk.nazwa || ""; document.getElementById("wym-new-od").value = pk.godz_od ? pk.godz_od.slice(0,5) : ""; }
};

async function loadWymagania() {
  const [s, e] = STATE.wybranyTydzien.split("|");
  const data = await api(`/wymagania?start=${s}&end=${e}`);
  STATE.wymagania = data;
  const stanMap = Object.fromEntries(STATE.stanowiska.map(x => [x.id, x]));
  
  // Grupowanie po dacie
  const days = {};
  data.forEach(w => { days[w.data] = days[w.data] || []; days[w.data].push(w); });

  let html = `<div class="grid grid-cols-1 xl:grid-cols-2 gap-6">`;
  if(data.length === 0) html += `<div class="col-span-full text-center p-8 text-slate-400 font-medium bg-white rounded-2xl border border-dashed border-slate-300">Brak zmian w tym tygodniu.</div>`;
  
  const nazwyDni = ["Niedziela", "Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota"];
  
  Object.keys(days).sort().forEach(dt => {
    const dObj = new Date(dt);
    html += `<div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
      <div class="bg-slate-50 px-5 py-3 border-b border-slate-200 flex justify-between items-center">
        <span class="font-bold text-slate-800">${nazwyDni[dObj.getDay()]}</span>
        <span class="text-xs font-mono text-slate-500 font-bold bg-white px-2 py-1 rounded border shadow-sm">${dt.split('-').reverse().join('.')}</span>
      </div>
      <div class="p-4 flex-1 space-y-3">`;
      
    days[dt].forEach(r => {
      html += `<div class="flex justify-between items-center border border-slate-100 bg-slate-50 rounded-xl p-3 shadow-sm hover:shadow-md transition-shadow">
        <div class="flex flex-col">
          <div class="font-bold text-sm text-slate-900">${stanMap[r.stanowisko_id]?.nazwa} ${r.rewir ? `<span class="text-blue-600 bg-blue-100/50 px-1.5 py-0.5 rounded text-xs ml-1">${r.rewir}</span>` : ""}</div>
          <div class="text-xs font-mono text-slate-500 mt-1">${ICONS.clock} ${r.godz_od ? r.godz_od.slice(0,5) : "Dowolna"}</div>
        </div>
        <div class="flex items-center gap-3">
          <div class="flex items-center bg-white border rounded-lg px-2 shadow-sm">
            <span class="text-xs font-bold text-slate-400 mr-2">Osób:</span>
            <input type="number" value="${r.liczba_osob}" onchange="updateWymaganieLiczba(${r.id}, this.value)" class="w-10 text-center py-1 font-bold outline-none text-sm text-slate-800">
          </div>
          <button onclick="deleteWymaganie(${r.id})" class="text-red-500 bg-red-50 hover:bg-red-500 hover:text-white p-2 rounded-lg transition-colors" title="Usuń zmianę">${ICONS.trash}</button>
        </div>
      </div>`;
    });
    html += `</div></div>`;
  });
  
  html += `</div>`;
  document.getElementById("wym-cards-cont").innerHTML = html;
}

async function addWymaganie() { const sid = document.getElementById("wym-new-stan").value; if(!sid) return; try { await api("/wymagania", "POST", { data: document.getElementById("wym-new-data").value, stanowisko_id: +sid, liczba_osob: +document.getElementById("wym-new-liczba").value, godz_od: document.getElementById("wym-new-od").value ? `${document.getElementById("wym-new-od").value}:00` : null, rewir: document.getElementById("wym-new-rewir").value || null }); loadWymagania(); } catch (e) { alert(e.message); } }
async function updateWymaganieLiczba(id, val) { const w = STATE.wymagania.find(x => x.id === id); if(!w) return; try { await api("/wymagania", "POST", { ...w, liczba_osob: +val }); loadWymagania(); } catch (e) { alert(e.message); } }
async function deleteWymaganie(id) { try { await api(`/wymagania/${id}`, "DELETE"); loadWymagania(); } catch (e) { alert(e.message); } }
window.kopiujWymagania = async function() { try { await api("/wymagania/kopiuj", "POST", { source_date: document.getElementById("kop-source").value, start_date: document.getElementById("kop-start").value, end_date: document.getElementById("kop-end").value }); loadWymagania(); } catch(e) { alert(e.message); } }

// ══════════════════════════════════════════════════════════════════════════
// GRAFIK
// ══════════════════════════════════════════════════════════════════════════
async function renderGrafik() {
  document.getElementById("grafik-content").innerHTML = `
    <div class="mb-6 flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
      <div class="flex flex-wrap gap-3 items-center bg-white border border-slate-200 p-2 rounded-2xl shadow-sm">
        ${zbudujDropdownTygodni("g-tydzien-sel", "loadGrafik")}
        <button onclick="autoAssign()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2.5 px-6 rounded-xl flex gap-2 items-center transition-colors shadow-sm">${ICONS.robot} Auto-Przydział AI</button>
        <button onclick="clearAssignments()" class="bg-white border border-red-200 text-red-600 hover:bg-red-50 py-2.5 px-6 rounded-xl font-bold transition-colors shadow-sm">Wyczyść Tabelę</button>
      </div>
    </div>
    <div id="niedobory-box"></div>
    <div class="overflow-x-auto bg-white rounded-2xl shadow-sm border border-slate-200 pb-2" id="grafik-table-cont"></div>`;
  loadGrafik();
}

async function loadGrafik() {
  await loadDicts(); const [s, e] = STATE.wybranyTydzien.split("|");
  const [przydzialy, dyspozycje, wymagania] = await Promise.all([api(`/przydzialy?start=${s}&end=${e}`), api(`/dyspozycje?start=${s}&end=${e}`), api(`/wymagania?start=${s}&end=${e}`)]);
  STATE.przydzialy = przydzialy; STATE.dyspozycje = dyspozycje; STATE.wymagania = wymagania;
  
  const dates = []; let cur = new Date(s); const endD = new Date(e);
  while (cur <= endD) { dates.push(cur.toISOString().slice(0, 10)); cur.setDate(cur.getDate() + 1); }
  const stanMap = Object.fromEntries(STATE.stanowiska.map(x => [x.id, x]));
  const przyMap = {}; przydzialy.forEach(a => { const k = `${a.data}_${a.pracownik_id}`; przyMap[k] = przyMap[k] || []; przyMap[k].push(a); });
  const dysMap = {}; dyspozycje.forEach(d => dysMap[`${d.data}_${d.pracownik_id}`] = d);
  const wymMap = {}; wymagania.forEach(w => { wymMap[w.data] = wymMap[w.data] || []; wymMap[w.data].push(w); });

  let thead = `<tr class="bg-slate-50 border-b border-slate-200"><th class="p-4 sticky left-0 z-10 bg-slate-50 min-w-[180px] border-r border-slate-200 text-left text-xs font-bold text-slate-500 uppercase tracking-wider shadow-[2px_0_5px_rgba(0,0,0,0.02)]">Pracownik</th>`;
  dates.forEach(dt => thead += `<th class="p-4 text-center border-r border-slate-200 font-bold text-slate-800 min-w-[140px]">${dt.split('-').reverse().slice(0,2).join('.')}</th>`); thead += `</tr>`;
  
  let tbody = "";
  STATE.pracownicy.filter(p => p.aktywny).forEach(p => {
    tbody += `<tr class="border-b border-slate-100 hover:bg-slate-50/50 transition-colors"><td class="p-4 sticky left-0 bg-white shadow-[2px_0_5px_rgba(0,0,0,0.02)] font-extrabold text-slate-900 border-r border-slate-200">${p.imie} ${p.nazwisko}</td>`;
    dates.forEach(dt => {
      const dys = dysMap[`${dt}_${p.id}`]; const pAt = przyMap[`${dt}_${p.id}`] || [];
      const isW = new Date(dt).getDay() === 0 || new Date(dt).getDay() === 6;
      const kwalIds = new Set((p.kwalifikacje || []).map(k => k.id));
      const szablony = (wymMap[dt] || []).filter(w => stanMap[w.stanowisko_id] && (!stanMap[w.stanowisko_id].tylko_weekend || isW) && kwalIds.has(w.stanowisko_id));
      
      let status = dys ? (dys.dostepnosc ? (dys.godz_od ? `Od ${dys.godz_od.slice(0,5)}` : "Dostępny") : "Niedostępny") : "brak";
      let cellBg = !dys ? 'bg-slate-50/50' : dys.dostepnosc ? 'bg-emerald-50/20' : 'bg-red-50/20';
      let statusColor = !dys ? 'text-slate-400 border-slate-200' : dys.dostepnosc ? 'text-emerald-700 bg-emerald-100 border-emerald-200' : 'text-red-700 bg-red-100 border-red-200';
      
      let cell = `<td class="p-3 border-r border-slate-100 ${cellBg} align-top"><div class="text-[10px] text-center font-bold mb-2 border rounded-md px-2 py-0.5 w-fit mx-auto ${statusColor}">${status}</div><div class="flex flex-col gap-2">`;
      
      pAt.forEach(a => {
        const stan = stanMap[a.stanowisko_id];
        const powiazanySzablon = szablony.find(w => w.stanowisko_id === a.stanowisko_id && w.godz_od === a.godz_od);
        const rewirNapis = powiazanySzablon && powiazanySzablon.rewir ? ` <span class="text-blue-600">(${powiazanySzablon.rewir})</span>` : "";
        cell += `<div class="bg-white border-l-4 border-blue-500 rounded-lg p-2 shadow-sm text-xs font-bold text-slate-800 text-left leading-snug border-t border-r border-b border-slate-100">${stan?.nazwa}${rewirNapis}<br><span class="font-mono font-medium text-slate-500 text-[10px] mt-1 block">${ICONS.clock} ${a.godz_od ? a.godz_od.slice(0,5) : 'Dowolnie'}</span><select onchange="changeAssignment(${a.id}, this.value)" class="w-full text-[10px] mt-1.5 border border-slate-200 bg-slate-50 rounded p-1 outline-none cursor-pointer text-slate-600 font-medium"><option>Zapisany</option><option value="REMOVE">Anuluj Zmianę</option></select></div>`;
      });
      if (dys?.dostepnosc && szablony.length > 0) {
        cell += `<select onchange="addAdvancedAssignment(this, '${dt}', ${p.id})" class="w-full text-xs p-1.5 border border-dashed border-slate-300 text-blue-600 cursor-pointer bg-white rounded-lg outline-none font-medium text-center shadow-sm hover:border-blue-400 transition-colors"><option>+ Dodaj</option>${szablony.map((w,i) => `<option value="${i}">${stanMap[w.stanowisko_id].nazwa} ${w.rewir ? `(${w.rewir})`:''} ${w.godz_od ? `[${w.godz_od.slice(0,5)}]`:''}</option>`).join("")}</select>`;
      }
      tbody += cell + `</div></td>`;
    });
    tbody += `</tr>`;
  });
  document.getElementById("grafik-table-cont").innerHTML = `<table class="w-full"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
}

async function addAdvancedAssignment(sel, dt, pId) { const i = sel.value; if(i===" " || i==="+ Dodaj") return; const isW = new Date(dt).getDay() === 0 || new Date(dt).getDay() === 6; const stanMap = Object.fromEntries(STATE.stanowiska.map(x => [x.id, x])); const p = STATE.pracownicy.find(x => x.id === pId); const kwalIds = new Set((p.kwalifikacje || []).map(k => k.id)); const w = (STATE.wymagania.filter(x => x.data === dt).filter(w => { const stan = stanMap[w.stanowisko_id]; return stan && (!stan.tylko_weekend || isW) && kwalIds.has(w.stanowisko_id); }))[i]; try { await api("/przydzialy", "POST", { data: dt, stanowisko_id: w.stanowisko_id, pracownik_id: pId, godz_od: w.godz_od }); loadGrafik(); } catch (e) { alert(e.message); sel.value="+ Dodaj"; } }
async function changeAssignment(aid, act) { if (act === "REMOVE") { await api(`/przydzialy/${aid}`, "DELETE"); loadGrafik(); } }
async function autoAssign() { document.getElementById("niedobory-box").innerHTML = `<div class="bg-blue-50 text-blue-800 p-4 rounded-xl font-bold border border-blue-200 animate-pulse mb-6 shadow-sm flex items-center gap-3">${ICONS.robot} Trwa procesowanie algorytmu...</div>`; try { await api(`/auto-assign?start=${STATE.wybranyTydzien.split("|")[0]}&end=${STATE.wybranyTydzien.split("|")[1]}`, "POST"); loadGrafik(); document.getElementById("niedobory-box").innerHTML = ''; } catch (e) { alert(e.message); } }
async function clearAssignments() { if (confirm("Czy na pewno wyczyścić cały grafik?")) { await api(`/przydzialy?start=${STATE.wybranyTydzien.split("|")[0]}&end=${STATE.wybranyTydzien.split("|")[1]}`, "DELETE"); loadGrafik(); } }

// Import/Export
document.getElementById("csv-upload-btn").addEventListener("click", async () => { const f = document.getElementById("csv-file"); if (!f.files.length) return; const fd = new FormData(); fd.append("file", f.files[0]); document.getElementById("import-preview").innerHTML = 'Analiza...'; try { const res = await fetch(`${API}/dyspozycje/import-csv`, { method: "POST", body: fd }); const data = await res.json(); document.getElementById("import-preview").innerHTML = `Zapisano ${data.zapisano} wierszy.`; f.value = ""; } catch (e) {} });
document.getElementById("eksport-btn").addEventListener("click", () => { const s = document.getElementById("eksport-start").value, e = document.getElementById("eksport-end").value; if (!s || !e) return; window.location.href = `${API}/eksport-csv?start=${s}&end=${e}`; });

// Uruchom
document.querySelector("nav button").click();