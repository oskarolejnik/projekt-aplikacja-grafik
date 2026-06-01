/**
 * Scheduler — frontend (vanilla JS, SPA)
 */

const API = "/api";
let STATE = { stanowiska: [], pracownicy: [], wymagania: [], dyspozycje: [], przydzialy: [], wybranyTydzien: "" };

document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach(b => b.classList.remove("active", "bg-blue-600", "text-white", "shadow-md"));
    document.querySelectorAll("section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active", "bg-blue-600", "text-white", "shadow-md");
    document.getElementById(btn.dataset.tab).classList.add("active");
    loadTab(btn.dataset.tab);
  });
});

function loadTab(tab) {
  switch (tab) {
    case "tab-pracownicy": renderPracownicy(); break;
    case "tab-stanowiska": renderStanowiska(); break;
    case "tab-wymagania":  renderWymagania();  break;
    case "tab-dyspozycje": break;
    case "tab-grafik":     renderGrafik();     break;
    case "tab-eksport":    break;
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
  return `<select id="${idAkapitu}" onchange="STATE.wybranyTydzien = this.value; ${funkcjaZdarzenia}();" class="bg-white border border-slate-300 text-slate-800 font-semibold text-sm rounded-lg focus:ring-blue-500 block w-64 p-2 shadow-sm cursor-pointer">${tygodnie.map(t => `<option value="${t.value}" ${STATE.wybranyTydzien === t.value ? "selected" : ""}>${t.label}</option>`).join("")}</select>`;
}

async function renderStanowiska() {
  await loadDicts();
  const cont = document.getElementById("stanowiska-content");
  
  let html = `
    <div class="mb-8"><h2 class="text-2xl font-bold text-slate-800">Zarządzanie Stanowiskami</h2></div>
    
    <div class="bg-white border rounded-xl shadow-sm p-6 mb-8">
      <h3 class="font-bold mb-4 text-slate-800">Nowe stanowisko (Kategoria Główna)</h3>
      <div class="flex gap-4 items-center">
        <input id="new-stan-nazwa" placeholder="Np. Sala, Bar..." class="border border-slate-300 rounded p-2 focus:ring-2 focus:ring-blue-500 outline-none w-64">
        <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" id="new-stan-weekend" class="w-4 h-4 text-blue-600"> <span class="font-medium text-slate-600">Tylko weekend</span></label>
        <button onclick="createStanowisko()" class="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-6 rounded-lg shadow-sm">Dodaj</button>
      </div>
    </div>

    <table class="w-full text-left bg-white rounded-xl shadow-sm overflow-hidden mb-8"><thead class="bg-slate-50 border-b border-slate-200"><tr><th class="p-4">ID</th><th>Nazwa</th><th>Tylko weekend</th><th>Akcje</th></tr></thead><tbody class="divide-y divide-slate-100">
      ${STATE.stanowiska.map(s => `<tr><td class="p-4 text-slate-500">#${s.id}</td><td><input id="sn-${s.id}" value="${s.nazwa}" class="border p-1 rounded w-full max-w-[200px]"></td><td><input type="checkbox" id="sw-${s.id}" ${s.tylko_weekend ? "checked" : ""}></td><td><button onclick="updateStanowisko(${s.id})" class="text-blue-600 bg-blue-50 hover:bg-blue-100 p-2 rounded mr-2 font-medium">Zapisz</button><button onclick="deleteStanowisko(${s.id})" class="text-red-600 bg-red-50 hover:bg-red-100 p-2 rounded font-medium">Usuń</button></td></tr>`).join("")}
    </tbody></table>
    
    <div class="bg-slate-50 border border-slate-200 rounded-xl shadow-sm p-6">
      <h3 class="text-lg font-bold text-slate-800 mb-2">Szablony Rewirów / Zmian dla stanowisk</h3>
      <p class="text-sm text-slate-500 mb-6">Dodaj gotowe szablony do stanowiska (np. BarR1, godz. 12:00). Dzięki temu przy tworzeniu grafiku wypełnią się one automatycznie.</p>
      
      <div class="flex flex-wrap items-end gap-4 mb-6 bg-white p-4 rounded-lg border border-slate-200 shadow-sm">
        <label class="flex flex-col gap-1 w-full sm:w-auto">
          <span class="text-sm font-medium text-slate-600">Do stanowiska:</span>
          <select id="new-pk-stan" class="border border-slate-300 rounded-lg px-4 py-2 bg-white">
             ${STATE.stanowiska.map(s => `<option value="${s.id}">${s.nazwa}</option>`).join("")}
          </select>
        </label>
        <label class="flex flex-col gap-1 w-full sm:w-auto">
          <span class="text-sm font-medium text-slate-600">Nazwa rewiru (np. BarR1):</span>
          <input id="new-pk-nazwa" placeholder="Wpisz rewir..." class="border border-slate-300 rounded-lg px-4 py-2">
        </label>
        <label class="flex flex-col gap-1 w-full sm:w-auto">
          <span class="text-sm font-medium text-slate-600">Godzina wejścia:</span>
          <input type="time" id="new-pk-od" class="border border-slate-300 rounded-lg px-4 py-2">
        </label>
        <button onclick="createPodkategoria()" class="bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-6 rounded-lg shadow-sm">
          + Dodaj Szablon
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        ${STATE.stanowiska.map(s => s.podkategorie && s.podkategorie.length > 0 ? `
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <h4 class="font-bold text-indigo-700 border-b border-slate-100 pb-2 mb-3">📌 ${s.nazwa}</h4>
            <div class="space-y-2">
              ${s.podkategorie.map(pk => `
                <div class="flex justify-between items-center bg-slate-50 p-2 rounded-lg border border-slate-100">
                  <div>
                    <div class="text-sm font-bold text-slate-800">${pk.nazwa}</div>
                    <div class="text-xs font-mono text-slate-500 mt-0.5">⏰ Od: ${pk.godz_od ? pk.godz_od.slice(0,5) : 'dowolna'}</div>
                  </div>
                  <button onclick="deletePodkategoria(${pk.id})" class="text-red-500 hover:text-white hover:bg-red-500 bg-red-50 px-2 py-1.5 rounded transition-colors text-xs font-bold border border-red-100">Usuń</button>
                </div>
              `).join("")}
            </div>
          </div>
        ` : "").join("")}
      </div>
    </div>
  `;
  cont.innerHTML = html;
}

// Funkcje API dla stanowisk i podkategorii
async function createStanowisko() {
  const nazwa = document.getElementById("new-stan-nazwa").value.trim();
  if (!nazwa) return alert("Podaj nazwę stanowiska.");
  try { await api("/stanowiska", "POST", { nazwa, tylko_weekend: document.getElementById("new-stan-weekend").checked }); renderStanowiska(); } catch (e) { alert(e.message); }
}
async function updateStanowisko(id) {
  try { await api(`/stanowiska/${id}`, "PUT", { nazwa: document.getElementById(`sn-${id}`).value.trim(), tylko_weekend: document.getElementById(`sw-${id}`).checked }); renderStanowiska(); } catch (e) { alert(e.message); }
}
async function deleteStanowisko(id) {
  if (confirm("Usunąć stanowisko?")) try { await api(`/stanowiska/${id}`, "DELETE"); renderStanowiska(); } catch (e) { alert(e.message); }
}

window.createPodkategoria = async function() {
  const sid = document.getElementById("new-pk-stan").value;
  const nazwa = document.getElementById("new-pk-nazwa").value.trim();
  let od = document.getElementById("new-pk-od").value;
  if (!nazwa) return alert("Podaj nazwę rewiru/szablonu.");
  od = od ? `${od}:00` : null;
  try { await api(`/stanowiska/${sid}/podkategorie`, "POST", { nazwa: nazwa, godz_od: od, godz_do: null }); renderStanowiska(); } catch (e) { alert(e.message); }
};

window.deletePodkategoria = async function(pid) {
  if(!confirm("Na pewno usunąć ten szablon rewiru?")) return;
  try { await api(`/podkategorie/${pid}`, "DELETE"); renderStanowiska(); } catch(e) { alert(e.message); }
};

// ══════════════════════════════════════════════════════════════════════════
// PRACOWNICY
// ══════════════════════════════════════════════════════════════════════════
async function renderPracownicy() {
  await loadDicts();
  const cont = document.getElementById("pracownicy-content");
  const stanChecks = (pracId, kwalIds, isNew = false) => `<div class="flex-1 overflow-y-auto pr-2 bg-slate-50 border border-slate-100 rounded-lg p-3">${STATE.stanowiska.map(s => `<label class="flex items-center gap-3 mb-2 cursor-pointer hover:bg-slate-200 p-1.5 rounded"><input type="checkbox" class="${isNew ? 'new-kwal' : `kwal-${pracId}`}" value="${s.id}" ${kwalIds.includes(s.id) ? "checked" : ""}><span>${s.nazwa}</span></label>`).join("")}</div>`;

  cont.innerHTML = `
    <div class="mb-8"><h2 class="text-2xl font-bold text-slate-800">Zarządzanie Pracownikami</h2></div>
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
      <div class="bg-blue-50 border-2 border-dashed border-blue-300 rounded-xl p-5 flex flex-col h-[420px]">
        <h3 class="text-lg font-bold text-blue-800 mb-2 shrink-0">➕ Nowy pracownik</h3>
        <div class="flex gap-2 shrink-0 mb-2"><input id="new-p-imie" class="w-full border border-blue-200 p-2 rounded" placeholder="Imię"><input id="new-p-nazwisko" class="w-full border border-blue-200 p-2 rounded" placeholder="Nazwisko"></div>
        <label class="shrink-0 mb-2 font-medium text-blue-800 flex items-center gap-2"><input type="checkbox" id="new-p-aktywny" checked class="w-4 h-4"> Aktywny</label>
        ${stanChecks('new', [], true)}
        <button onclick="createPracownik()" class="w-full bg-blue-600 text-white font-bold p-2.5 rounded-lg mt-4 shrink-0 shadow-sm">Dodaj pracownika</button>
      </div>
      ${STATE.pracownicy.map(p => {
        const kwalIds = (p.kwalifikacje || []).map(k => k.id);
        return `<div class="bg-white border rounded-xl shadow-sm p-5 flex flex-col h-[420px]">
          <div class="shrink-0 flex justify-between mb-3"><div class="flex flex-col w-full pr-2"><input id="pi-${p.id}" value="${p.imie}" class="font-bold text-lg border-b border-transparent focus:border-blue-500 outline-none"><input id="pn-${p.id}" value="${p.nazwisko}" class="font-medium text-slate-600 border-b border-transparent focus:border-blue-500 outline-none mt-1"></div></div>
          <label class="shrink-0 mb-2 text-sm font-medium flex items-center gap-2"><input type="checkbox" id="pa-${p.id}" ${p.aktywny ? "checked" : ""} class="w-4 h-4"> ${p.aktywny ? '<span class="text-emerald-600">Aktywny</span>' : '<span class="text-slate-400">Zablokowany</span>'}</label>
          ${stanChecks(p.id, kwalIds)}
          <div class="shrink-0 flex gap-2 mt-4"><button onclick="updatePracownik(${p.id})" class="flex-1 bg-slate-100 hover:bg-slate-200 p-2.5 rounded-lg border font-medium">Zapisz</button><button onclick="deletePracownik(${p.id})" class="text-red-500 bg-red-50 hover:bg-red-100 p-2.5 rounded-lg font-bold">Usuń</button></div>
        </div>`;
      }).join("")}
    </div>`;
}

async function createPracownik() {
  const imie = document.getElementById("new-p-imie").value.trim(), nazwisko = document.getElementById("new-p-nazwisko").value.trim();
  if (!imie || !nazwisko) return alert("Podaj imię i nazwisko.");
  try { await api("/pracownicy", "POST", { imie, nazwisko, aktywny: document.getElementById("new-p-aktywny").checked, kwalifikacje_ids: [...document.querySelectorAll(".new-kwal:checked")].map(el => +el.value) }); renderPracownicy(); } catch (e) { alert(e.message); }
}
async function updatePracownik(id) {
  try { await api(`/pracownicy/${id}`, "PUT", { imie: document.getElementById(`pi-${id}`).value.trim(), nazwisko: document.getElementById(`pn-${id}`).value.trim(), aktywny: document.getElementById(`pa-${id}`).checked, kwalifikacje_ids: [...document.querySelectorAll(`.kwal-${id}:checked`)].map(el => +el.value) }); renderPracownicy(); } catch (e) { alert(e.message); }
}
async function deletePracownik(id) { if (confirm("Usunąć?")) try { await api(`/pracownicy/${id}`, "DELETE"); renderPracownicy(); } catch (e) { alert(e.message); } }

// ══════════════════════════════════════════════════════════════════════════
// WYMAGANIA (Z automatycznym wczytywaniem szablonów)
// ══════════════════════════════════════════════════════════════════════════
async function renderWymagania() {
  await loadDicts();
  const cont = document.getElementById("wymagania-content");
  
  cont.innerHTML = `
    <div class="mb-8 flex justify-between items-end">
      <div><h2 class="text-2xl font-bold text-slate-800">Wymagania Personalne</h2><p class="text-slate-500">Ilu pracowników potrzeba na dany dzień.</p></div>
      <div class="bg-white p-2 rounded-xl border border-slate-200 shadow-sm">${zbudujDropdownTygodni("wym-tydzien-sel", "loadWymagania")}</div>
    </div>
    
    <div id="wym-table-cont" class="bg-white rounded-xl shadow-sm border border-slate-200 mb-8 overflow-x-auto"></div>
    
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <fieldset class="border border-slate-200 p-6 bg-white rounded-xl shadow-sm">
        <legend class="text-lg font-bold text-emerald-700 px-2 bg-white">➕ Zaplanuj Zmianę</legend>
        
        <div class="space-y-4 mt-2">
          <div class="grid grid-cols-2 gap-4">
            <label class="flex flex-col gap-1"><span class="text-sm font-medium text-slate-600">Data</span><input type="date" id="wym-new-data" value="${new Date().toISOString().slice(0, 10)}" class="border border-slate-300 rounded-lg px-3 py-2"></label>
            <label class="flex flex-col gap-1">
              <span class="text-sm font-medium text-slate-600">Stanowisko (Wymóg)</span>
              <select id="wym-new-stan" onchange="updateSubcatDropdown()" class="border border-slate-300 bg-white rounded-lg px-3 py-2">
                <option value="">-- Wybierz --</option>
                ${STATE.stanowiska.map(s => `<option value="${s.id}">${s.nazwa}</option>`).join("")}
              </select>
            </label>
          </div>

          <div id="subcat-container" class="bg-indigo-50 border border-indigo-200 p-3 rounded-lg" style="display:none;">
            <label class="flex flex-col gap-1 w-full">
              <span class="text-sm font-bold text-indigo-700 flex items-center gap-1">✨ Gotowy szablon (Automatycznie wypełni dane)</span>
              <select id="wym-new-subcat" onchange="applySubcatTemplate()" class="border border-indigo-300 bg-white rounded px-3 py-2 cursor-pointer font-medium text-indigo-900"></select>
            </label>
          </div>

          <div class="grid grid-cols-3 gap-4 border-t border-slate-100 pt-4">
            <label class="flex flex-col gap-1"><span class="text-sm font-medium text-slate-600">Godz. OD</span><input type="time" id="wym-new-od" class="border border-slate-300 rounded-lg px-2 py-2"></label>
            <label class="flex flex-col gap-1"><span class="text-sm font-medium text-slate-600">Godz. DO</span><input type="time" id="wym-new-do" class="border border-slate-300 rounded-lg px-2 py-2"></label>
            <label class="flex flex-col gap-1"><span class="text-sm font-medium text-slate-600">Osób na zmianę</span><input type="number" id="wym-new-liczba" value="1" min="1" class="border border-slate-300 rounded-lg px-3 py-2 font-bold"></label>
          </div>
          
          <label class="flex flex-col gap-1"><span class="text-sm font-medium text-slate-600">Nazwa Rewiru / Strefy</span><input id="wym-new-rewir" placeholder="np. BarR1, Ogród..." class="border border-slate-300 rounded-lg px-3 py-2"></label>
          
          <button onclick="addWymaganie()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 w-full mt-2 rounded-lg shadow-sm transition-colors">Dodaj Zmianę do planu</button>
        </div>
      </fieldset>
    </div>`;
  loadWymagania();
}

// Logika pobierająca podkategorie na żywo z zapisanego STATE
window.updateSubcatDropdown = function() {
  const sid = +document.getElementById("wym-new-stan").value;
  const s = STATE.stanowiska.find(x => x.id === sid);
  const cont = document.getElementById("subcat-container");
  const sel = document.getElementById("wym-new-subcat");

  if (s && s.podkategorie && s.podkategorie.length > 0) {
      let opts = `<option value="">-- Ignoruj szablony (Wpisz ręcznie poniżej) --</option>`;
      s.podkategorie.forEach(pk => {
          opts += `<option value="${pk.id}">${pk.nazwa} (Godz. Wejścia: ${pk.godz_od ? pk.godz_od.slice(0,5) : 'Brak'})</option>`;
      });
      sel.innerHTML = opts;
      cont.style.display = "block";
  } else {
      sel.innerHTML = "";
      cont.style.display = "none";
  }
};

window.applySubcatTemplate = function() {
  const sid = +document.getElementById("wym-new-stan").value;
  const pid = +document.getElementById("wym-new-subcat").value;
  const s = STATE.stanowiska.find(x => x.id === sid);
  if(!s) return;
  const pk = s.podkategorie.find(x => x.id === pid);
  
  if(pk) {
    document.getElementById("wym-new-rewir").value = pk.nazwa || "";
    document.getElementById("wym-new-od").value = pk.godz_od ? pk.godz_od.slice(0,5) : "";
    document.getElementById("wym-new-do").value = pk.godz_do ? pk.godz_do.slice(0,5) : "";
  }
};

async function loadWymagania() {
  const bocznyZasieg = STATE.wybranyTydzien.split("|");
  const data = await api(`/wymagania?start=${bocznyZasieg[0]}&end=${bocznyZasieg[1]}`);
  STATE.wymagania = data;
  const stanMap = Object.fromEntries(STATE.stanowiska.map(s => [s.id, s]));
  let html = `<table class="w-full text-left"><thead class="bg-slate-50 border-b border-slate-200"><tr><th class="p-4 font-semibold">Data</th><th class="font-semibold">Wymagana Pozycja (Rewir)</th><th class="font-semibold">Godziny</th><th class="text-center font-semibold">Osoby</th><th class="font-semibold">Akcje</th></tr></thead><tbody class="divide-y divide-slate-100">`;
  
  if(data.length === 0) { html += `<tr><td colspan="5" class="text-center p-8 text-slate-400">Brak zmian w wybranym tygodniu.</td></tr>`; }
  
  data.forEach(r => {
    html += `<tr class="hover:bg-slate-50"><td class="p-4 font-medium text-slate-900">${r.data}</td><td><span class="font-bold text-slate-800">${stanMap[r.stanowisko_id]?.nazwa}</span> ${r.rewir ? `<span class="text-blue-600 font-bold ml-1">(${r.rewir})</span>` : ""}</td><td><span class="bg-slate-100 border border-slate-200 px-2 py-1 rounded font-mono text-xs">${r.godz_od ? `${r.godz_od.slice(0,5)} - ${r.godz_do ? r.godz_do.slice(0,5) : 'Koniec'}` : "Cała Zmiana"}</span></td><td class="text-center"><input type="number" value="${r.liczba_osob}" onchange="updateWymaganieLiczba(${r.id}, this.value)" class="w-16 border border-slate-300 rounded text-center py-1 outline-none focus:border-blue-500 font-bold"></td><td><button onclick="deleteWymaganie(${r.id})" class="text-red-500 hover:text-red-700 bg-red-50 px-3 py-1.5 rounded-lg text-sm font-bold border border-red-100">Usuń</button></td></tr>`;
  });
  html += `</tbody></table>`;
  document.getElementById("wym-table-cont").innerHTML = html;
}

async function addWymaganie() {
  const sid = document.getElementById("wym-new-stan").value;
  if(!sid) return alert("Musisz wybrać stanowisko główne (np. Sala)!");
  try { await api("/wymagania", "POST", { data: document.getElementById("wym-new-data").value, stanowisko_id: +sid, liczba_osob: +document.getElementById("wym-new-liczba").value, godz_od: document.getElementById("wym-new-od").value ? `${document.getElementById("wym-new-od").value}:00` : null, godz_do: document.getElementById("wym-new-do").value ? `${document.getElementById("wym-new-do").value}:00` : null, rewir: document.getElementById("wym-new-rewir").value || null }); loadWymagania(); } catch (e) { alert(e.message); }
}
async function updateWymaganieLiczba(id, val) {
  const w = STATE.wymagania.find(x => x.id === id); if(!w) return;
  try { await api("/wymagania", "POST", { ...w, liczba_osob: +val }); loadWymagania(); } catch (e) { alert(e.message); }
}
async function deleteWymaganie(id) { try { await api(`/wymagania/${id}`, "DELETE"); loadWymagania(); } catch (e) { alert(e.message); } }


// ══════════════════════════════════════════════════════════════════════════
// GRAFIK
// ══════════════════════════════════════════════════════════════════════════
async function renderGrafik() {
  document.getElementById("grafik-content").innerHTML = `
    <div class="mb-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-4"><h2 class="text-2xl font-bold">Interaktywny Grafik</h2>
      <div class="flex flex-wrap gap-2 items-center bg-white border border-slate-200 p-2 rounded-xl shadow-sm">${zbudujDropdownTygodni("g-tydzien-sel", "loadGrafik")}<button onclick="autoAssign()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold p-2.5 rounded-lg transition-colors flex gap-2 items-center">🤖 Auto-Przydział</button><button onclick="clearAssignments()" class="bg-white border border-red-200 text-red-600 hover:bg-red-50 p-2.5 rounded-lg font-medium transition-colors">Wyczyść</button></div>
    </div><div id="niedobory-box"></div><div class="overflow-x-auto bg-white rounded-xl shadow-sm border pb-2" id="grafik-table-cont"></div>`;
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

  let thead = `<tr class="bg-slate-100 border-b"><th class="p-3 sticky left-0 z-10 bg-slate-100 min-w-[160px] border-r">Pracownik</th>`;
  dates.forEach(dt => thead += `<th class="p-3 text-center border-r font-semibold">${dt.slice(5)}</th>`); thead += `</tr>`;
  
  let tbody = "";
  STATE.pracownicy.filter(p => p.aktywny).forEach(p => {
    tbody += `<tr class="border-b hover:bg-slate-50"><td class="p-3 sticky left-0 bg-white shadow-sm font-bold border-r text-slate-800">${p.imie} ${p.nazwisko}</td>`;
    dates.forEach(dt => {
      const dys = dysMap[`${dt}_${p.id}`]; const pAt = przyMap[`${dt}_${p.id}`] || [];
      const isW = new Date(dt).getDay() === 0 || new Date(dt).getDay() === 6;
      const kwalIds = new Set((p.kwalifikacje || []).map(k => k.id));
      const szablony = (wymMap[dt] || []).filter(w => stanMap[w.stanowisko_id] && (!stanMap[w.stanowisko_id].tylko_weekend || isW) && kwalIds.has(w.stanowisko_id));
      
      let status = dys ? (dys.dostepnosc ? (dys.godz_od ? `✅ ${dys.godz_od.slice(0,5)}-${dys.godz_do ? dys.godz_do.slice(0,5):'Koniec'}` : "✅ Cały dzień") : "❌ Niedostępny") : "brak";
      let cellBg = !dys ? 'bg-slate-50' : dys.dostepnosc ? 'bg-emerald-50/30' : 'bg-red-50/50';
      let statusColor = !dys ? 'text-slate-400' : dys.dostepnosc ? 'text-emerald-700 bg-emerald-100' : 'text-red-700 bg-red-100';
      
      let cell = `<td class="p-2 border-r ${cellBg} align-top"><div class="text-[10px] text-center font-bold mb-1 border rounded px-1 w-fit mx-auto ${statusColor}">${status}</div><div class="flex flex-col gap-1.5 mt-1">`;
      
      pAt.forEach(a => {
        const stan = stanMap[a.stanowisko_id];
        const powiazanySzablon = szablony.find(w => w.stanowisko_id === a.stanowisko_id && w.godz_od === a.godz_od);
        const rewirNapis = powiazanySzablon && powiazanySzablon.rewir ? ` <span class="text-blue-600">(${powiazanySzablon.rewir})</span>` : "";
        cell += `<div class="bg-white border-l-4 border-blue-500 border rounded p-1.5 shadow-sm text-[11px] font-bold text-left leading-tight">${stan?.nazwa}${rewirNapis}<br><span class="font-mono font-normal text-slate-500 text-[10px]">⏰ ${a.godz_od ? a.godz_od.slice(0,5) : 'Cała zmiana'}</span><select onchange="changeAssignment(${a.id}, this.value)" class="w-full text-[10px] mt-1 border border-slate-200 rounded p-0.5 outline-none cursor-pointer"><option>Przypisany</option><option value="REMOVE">❌ Usuń zmianę</option></select></div>`;
      });
      if (dys?.dostepnosc && szablony.length > 0) {
        cell += `<select onchange="addAdvancedAssignment(this, '${dt}', ${p.id})" class="w-full text-[10px] p-1 border border-dashed border-slate-300 rounded text-blue-600 font-medium cursor-pointer bg-white"><option>+ Dodaj zmianę</option>${szablony.map((w,i) => `<option value="${i}">${stanMap[w.stanowisko_id].nazwa} ${w.rewir ? `(${w.rewir})`:''} ${w.godz_od ? `[${w.godz_od.slice(0,5)}]`:''}</option>`).join("")}</select>`;
      }
      tbody += cell + `</div></td>`;
    });
    tbody += `</tr>`;
  });
  document.getElementById("grafik-table-cont").innerHTML = `<table class="w-full"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
}

async function addAdvancedAssignment(sel, dt, pId) {
  const i = sel.value; if(i===" " || i==="+ Dodaj zmianę") return;
  const isW = new Date(dt).getDay() === 0 || new Date(dt).getDay() === 6;
  const stanMap = Object.fromEntries(STATE.stanowiska.map(x => [x.id, x]));
  const p = STATE.pracownicy.find(x => x.id === pId);
  const kwalIds = new Set((p.kwalifikacje || []).map(k => k.id));
  
  const w = (STATE.wymagania.filter(x => x.data === dt).filter(w => {
    const stan = stanMap[w.stanowisko_id];
    return stan && (!stan.tylko_weekend || isW) && kwalIds.has(w.stanowisko_id);
  }))[i];
  
  try { await api("/przydzialy", "POST", { data: dt, stanowisko_id: w.stanowisko_id, pracownik_id: pId, godz_od: w.godz_od, godz_do: w.godz_do }); loadGrafik(); } catch (e) { alert(e.message); sel.value="+ Dodaj zmianę"; }
}

async function changeAssignment(aid, act) { if (act === "REMOVE") { await api(`/przydzialy/${aid}`, "DELETE"); loadGrafik(); } }
async function autoAssign() { document.getElementById("niedobory-box").innerHTML = '<div class="bg-blue-50 text-blue-700 p-4 rounded-lg font-medium border border-blue-200 animate-pulse mb-4">⚙️ AI analizuje kwalifikacje i dyspozycyjność... Trwa generowanie harmonogramu.</div>'; try { await api(`/auto-assign?start=${STATE.wybranyTydzien.split("|")[0]}&end=${STATE.wybranyTydzien.split("|")[1]}`, "POST"); loadGrafik(); document.getElementById("niedobory-box").innerHTML = ''; } catch (e) { alert(e.message); } }
async function clearAssignments() { if (confirm("Wyczyścić bieżący grafik?")) { await api(`/przydzialy?start=${STATE.wybranyTydzien.split("|")[0]}&end=${STATE.wybranyTydzien.split("|")[1]}`, "DELETE"); loadGrafik(); } }
// ══════════════════════════════════════════════════════════════════════════
// IMPORT DYSPOZYCJI (CSV)
// ══════════════════════════════════════════════════════════════════════════
document.getElementById("csv-upload-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("csv-file");
  if (!fileInput.files.length) return alert("Najpierw wybierz plik CSV z dysku.");
  
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  
  const previewCont = document.getElementById("import-preview");
  previewCont.innerHTML = '<div class="text-blue-600 font-medium animate-pulse p-2">⏳ Trwa wgrywanie i analizowanie pliku...</div>';

  try {
    const res = await fetch(`${API}/dyspozycje/import-csv`, { method: "POST", body: formData });
    const data = await res.json();
    
    if (!res.ok) throw new Error(data.detail || "Wystąpił błąd podczas importu.");

    // Stylizacja sukcesu
    let html = `<div class="bg-emerald-50 text-emerald-700 p-4 rounded-lg font-bold border border-emerald-200 mb-4 shadow-sm">✅ Import zakończony! Zapisano: ${data.zapisano} wierszy.</div>`;

    // Tabelka z podglądem dodanych dyspozycji
    if (data.podglad && data.podglad.length) {
      html += `
        <h3 class="font-bold text-slate-800 mb-2">Podgląd pierwszych wierszy:</h3>
        <div class="overflow-x-auto border border-slate-200 rounded-lg mb-4">
          <table class="w-full text-sm text-left">
            <thead class="bg-slate-100 text-slate-600">
              <tr><th class="p-2">Pracownik</th><th class="p-2">Data</th><th class="p-2 text-center">Dostępność</th><th class="p-2">Od</th><th class="p-2">Do</th></tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${data.podglad.map(r => `
                <tr class="hover:bg-slate-50">
                  <td class="p-2 font-medium">${r.pracownik}</td>
                  <td class="p-2">${r.data}</td>
                  <td class="p-2 text-center">${r.dostepnosc ? '<span class="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-bold text-xs">TAK</span>' : '<span class="bg-red-100 text-red-700 px-2 py-0.5 rounded font-bold text-xs">NIE</span>'}</td>
                  <td class="p-2 font-mono">${r.od || '-'}</td>
                  <td class="p-2 font-mono">${r.do || '-'}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    }

    // Tabelka z błędami (jeśli wiersze w CSV były błędne)
    if (data.konflikty && data.konflikty.length) {
      html += `
        <h3 class="font-bold text-red-700 mt-4 mb-2">⚠️ Pominięte wiersze (błędy)</h3>
        <div class="overflow-x-auto border border-red-200 rounded-lg">
          <table class="w-full text-sm text-left">
            <thead class="bg-red-50 text-red-800">
              <tr><th class="p-2 w-20">Wiersz</th><th class="p-2">Opis problemu</th></tr>
            </thead>
            <tbody class="divide-y divide-red-100">
              ${data.konflikty.map(k => `
                <tr class="bg-red-50/30">
                  <td class="p-2 font-bold text-red-700">#${k.wiersz}</td>
                  <td class="p-2 text-red-600">${k.problem}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    }

    previewCont.innerHTML = html;
    fileInput.value = ""; // Czyści pole wyboru pliku po pomyślnym imporcie
  } catch (e) {
    previewCont.innerHTML = `<div class="bg-red-50 text-red-700 p-4 rounded-lg font-bold border border-red-200 shadow-sm">❌ Błąd importu: ${e.message}</div>`;
  }
});

// ══════════════════════════════════════════════════════════════════════════
// EKSPORT GRAFIKU DO CSV
// ══════════════════════════════════════════════════════════════════════════
document.getElementById("eksport-btn").addEventListener("click", () => {
  const start = document.getElementById("eksport-start").value;
  const end = document.getElementById("eksport-end").value;
  
  if (!start || !end) {
    return alert("Wybierz zakres dat (Od - Do) przed próbą eksportu grafiku!");
  }
  
  // Pobra plik z backendu 
  window.location.href = `${API}/eksport-csv?start=${start}&end=${end}`;
});
document.querySelector("nav button").click();