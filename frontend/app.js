/**
 * Scheduler — frontend (vanilla JS, SPA)
 * Komunikuje się z FastAPI przez /api/*
 * Wersja z inteligentnym, globalnym zapamiętywaniem wybranego tygodnia
 */

const API = "/api";

// ── stan aplikacji ──────────────────────────────────────────────────────
let STATE = {
  stanowiska: [],
  pracownicy: [],
  wymagania:  [],
  dyspozycje: [],
  przydzialy: [],
  wybranyTydzien: "" // Globalna pamięć wybranego tygodnia (format: "YYYY-MM-DD|YYYY-MM-DD")
};

// ── nawigacja zakładkami ────────────────────────────────────────────────
document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
    document.querySelectorAll("section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    loadTab(btn.dataset.tab);
  });
});

function loadTab(tab) {
  switch (tab) {
    case "tab-pracownicy":   renderPracownicy(); break;
    case "tab-stanowiska":   renderStanowiska(); break;
    case "tab-wymagania":    renderWymagania();  break;
    case "tab-dyspozycje":   /* nic — upload */ break;
    case "tab-grafik":       renderGrafik();     break;
    case "tab-eksport":      renderEksport();    break;
  }
}

// ── fetch helper ────────────────────────────────────────────────────────
async function api(path, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API + path, opts);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// ── ładowanie słowników ─────────────────────────────────────────────────
async function loadDicts() {
  STATE.stanowiska = await api("/stanowiska");
  STATE.pracownicy = await api("/pracownicy");
}

// ── GENERATOR TYGODNI (ŚRODA - WTOREK) ───────────────────────────────────
function generujOpcjeTygodni() {
  const opcje = [];
  const dzis = new Date();
  
  const startSroda = new Date(dzis);
  const ladowanyDzien = dzis.getDay(); 
  let przesuniecie = ladowanyDzien - 3;
  if (przesuniecie < 0) przesuniecie += 7;
  startSroda.setDate(dzis.getDate() - przesuniecie);

  for (let i = -2; i <= 5; i++) {
    const sroda = new Date(startSroda);
    sroda.setDate(startSroda.getDate() + (i * 7));
    
    const wtorek = new Date(sroda);
    wtorek.setDate(sroda.getDate() + 6);
    
    const srodaStr = sroda.toISOString().slice(0, 10);
    const wtorekStr = wtorek.toISOString().slice(0, 10);
    
    const fSroda = srodaStr.split('-').reverse().join('.');
    const fWtorek = wtorekStr.split('-').reverse().join('.');
    
    const value = `${srodaStr}|${wtorekStr}`;
    
    // Jeśli to pierwsze uruchomienie i pamięć jest pusta, ustawiamy bieżący tydzień jako domyślny
    if (!STATE.wybranyTydzien && i === 0) {
      STATE.wybranyTydzien = value;
    }
    
    opcje.push({
      value: value,
      label: `${fSroda} — ${fWtorek}`
    });
  }
  return opcje;
}

// Buduje dropdown i dba o to, by zaznaczony był tydzień zapisany w STATE
function zbudujDropdownTygodni(idAkapitu, funkcjaZdarzenia) {
  const tygodnie = generujOpcjeTygodni();
  return `
    <select id="${idAkapitu}" onchange="STATE.wybranyTydzien = this.value; ${funkcjaZdarzenia}();" style="font-weight: 600; width: 260px; cursor: pointer;">
      ${tygodnie.map(t => `<option value="${t.value}" ${STATE.wybranyTydzien === t.value ? "selected" : ""}>${t.label}</option>`).join("")}
    </select>
  `;
}


// ══════════════════════════════════════════════════════════════════════════
// STANOWISKA
// ══════════════════════════════════════════════════════════════════════════

async function renderStanowiska() {
  await loadDicts();
  const cont = document.getElementById("stanowiska-content");
  let html = `
    <h2>Stanowiska</h2>
    <table>
      <tr><th>ID</th><th>Nazwa</th><th>Tylko weekend</th><th>Akcje</th></tr>
      ${STATE.stanowiska.map(s => `
        <tr id="stan-row-${s.id}">
          <td>${s.id}</td>
          <td><input id="sn-${s.id}" value="${s.nazwa}" style="width:120px"></td>
          <td><input type="checkbox" id="sw-${s.id}" ${s.tylko_weekend ? "checked" : ""}></td>
          <td>
            <button onclick="updateStanowisko(${s.id})">Zapisz</button>
            <button class="danger" onclick="deleteStanowisko(${s.id})">Usuń</button>
          </td>
        </tr>`).join("")}
    </table>
    <fieldset>
      <legend>Nowe stanowisko</legend>
      <div class="row">
        <label>Nazwa: <input id="new-stan-nazwa" placeholder="np. Kasa"></label>
        <label><input type="checkbox" id="new-stan-weekend"> Tylko weekend</label>
        <button onclick="createStanowisko()">Dodaj</button>
      </div>
    </fieldset>
  `;
  cont.innerHTML = html;
}

async function createStanowisko() {
  const nazwa = document.getElementById("new-stan-nazwa").value.trim();
  const tylko_weekend = document.getElementById("new-stan-weekend").checked;
  if (!nazwa) return alert("Podaj nazwę stanowiska.");
  try {
    await api("/stanowiska", "POST", { nazwa, tylko_weekend });
    renderStanowiska();
  } catch (e) { alert(e.message); }
}

async function updateStanowisko(id) {
  const nazwa = document.getElementById(`sn-${id}`).value.trim();
  const tylko_weekend = document.getElementById(`sw-${id}`).checked;
  try {
    await api(`/stanowiska/${id}`, "PUT", { nazwa, tylko_weekend });
    renderStanowiska();
  } catch (e) { alert(e.message); }
}

async function deleteStanowisko(id) {
  if (!confirm("Usunąć stanowisko?")) return;
  try {
    await api(`/stanowiska/${id}`, "DELETE");
    renderStanowiska();
  } catch (e) { alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════
// PRACOWNICI
// ══════════════════════════════════════════════════════════════════════════

async function renderPracownicy() {
  await loadDicts();
  const cont = document.getElementById("pracownicy-content");

  const stanChecks = (pracId, kwalIds) => `
    <div class="kwalifikacje-container">
      ${STATE.stanowiska.map(s => `
        <label class="kwalifikacja-item">
          <input type="checkbox" class="kwal-${pracId}" value="${s.id}"
            ${kwalIds.includes(s.id) ? "checked" : ""}>
          <span>${s.nazwa}</span>
        </label>
      `).join("")}
    </div>
  `;

  let html = `
    <h2>Zarządzanie pracownikami</h2>
    <table>
      <tr><th>ID</th><th>Imię</th><th>Nazwisko</th><th>Aktywny</th><th>Kwalifikacje (Stanowiska)</th><th>Akcje</th></tr>
      ${STATE.pracownicy.map(p => {
        const kwalIds = (p.kwalifikacje || []).map(k => k.id);
        return `<tr>
          <td>${p.id}</td>
          <td><input id="pi-${p.id}" value="${p.imie}" style="width:100px"></td>
          <td><input id="pn-${p.id}" value="${p.nazwisko}" style="width:130px"></td>
          <td>
            <label class="kwalifikacja-item" style="padding: 6px 10px; margin: 0;">
              <input type="checkbox" id="pa-${p.id}" ${p.aktywny ? "checked" : ""}>
              <span>Aktywny</span>
            </label>
          </td>
          <td>${stanChecks(p.id, kwalIds)}</td>
          <td>
            <button onclick="updatePracownik(${p.id})">Zapisz</button>
            <button class="danger" onclick="deletePracownik(${p.id})">Usuń</button>
          </td>
        </tr>`;
      }).join("")}
    </table>
    
    <fieldset style="margin-top: 30px;">
      <legend>Nowy pracownik</legend>
      <div class="row" style="margin-bottom: 16px;">
        <label>Imię: <input id="new-p-imie" style="width:150px" placeholder="np. Jan"></label>
        <label>Nazwisko: <input id="new-p-nazwisko" style="width:180px" placeholder="np. Kowalski"></label>
        <label style="flex-direction: row; align-items: center; gap: 8px; margin-top: 25px; cursor: pointer;">
          <input type="checkbox" id="new-p-aktywny" checked style="width:18px; height:18px; accent-color: #3b82f6;"> Aktywny pracownik
        </label>
      </div>
      
      <div style="margin: 16px 0;">
        <p style="font-weight: 600; color: #334155; margin-bottom: 8px;">Kwalifikacje i uprawnienia stanowiskowe:</p>
        <div class="kwalifikacje-container">
          ${STATE.stanowiska.map(s => `
            <label class="kwalifikacja-item">
              <input type="checkbox" class="new-kwal" value="${s.id}">
              <span>${s.nazwa}</span>
            </label>
          `).join("")}
        </div>
      </div>
      
      <button onclick="createPracownik()">Dodaj nowego pracownika</button>
    </fieldset>
  `;
  cont.innerHTML = html;
}

async function createPracownik() {
  const imie     = document.getElementById("new-p-imie").value.trim();
  const nazwisko = document.getElementById("new-p-nazwisko").value.trim();
  const aktywny  = document.getElementById("new-p-aktywny").checked;
  const kwalifikacje_ids = [...document.querySelectorAll(".new-kwal:checked")].map(el => +el.value);
  if (!imie || !nazwisko) return alert("Podaj imię i nazwisko.");
  try {
    await api("/pracownicy", "POST", { imie, nazwisko, aktywny, kwalifikacje_ids });
    renderPracownicy();
  } catch (e) { alert(e.message); }
}

async function updatePracownik(id) {
  const imie     = document.getElementById(`pi-${id}`).value.trim();
  const nazwisko = document.getElementById(`pn-${id}`).value.trim();
  const aktywny  = document.getElementById(`pa-${id}`).checked;
  const kwalifikacje_ids = [...document.querySelectorAll(`.kwal-${id}:checked`)].map(el => +el.value);
  try {
    await api(`/pracownicy/${id}`, "PUT", { imie, nazwisko, aktywny, kwalifikacje_ids });
    renderPracownicy();
  } catch (e) { alert(e.message); }
}

async function deletePracownik(id) {
  if (!confirm("Usunąć pracownika?")) return;
  try {
    await api(`/pracownicy/${id}`, "DELETE");
    renderPracownicy();
  } catch (e) { alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════
// WYMAGANIA DNIA
// ══════════════════════════════════════════════════════════════════════════

async function renderWymagania() {
  await loadDicts();
  const cont = document.getElementById("wymagania-content");
  const today = new Date().toISOString().slice(0, 10);

  cont.innerHTML = `
    <h2>Wymagania i Szablony Zmian</h2>
    
    <fieldset>
      <legend>🔍 Wybierz tydzień rozliczeniowy (Śr — Wt)</legend>
      <div class="row">
        <label>Tydzień: ${zbudujDropdownTygodni("wym-tydzien-sel", "loadWymagania")}</label>
      </div>
    </fieldset>
    
    <div id="wym-table-cont" style="margin: 20px 0;"></div>
    
    <fieldset style="margin-top: 25px; background: #fafafa;">
      <legend>➕ Dodaj nową zmianę / rewir do planu</legend>
      
      <div class="row" style="margin-bottom: 12px;">
        <label>Data zmiany: <input type="date" id="wym-new-data" value="${today}"></label>
        
        <label>Stanowisko:
          <select id="wym-new-stan">
            ${STATE.stanowiska.map(s => `<option value="${s.id}">${s.nazwa}${s.tylko_weekend ? " [W]" : ""}</option>`).join("")}
          </select>
        </label>
        
        <label>Liczba osób: <input type="number" id="wym-new-liczba" value="1" min="1" style="width:70px"></label>
      </div>
      
      <div class="row" style="border-top: 1px solid #e2e8f0; padding-top: 15px; margin-top: 10px;">
        <label>Godzina OD: <input type="time" id="wym-new-od" value="10:00"></label>
        <label>Godzina DO: <input type="time" id="wym-new-do" value="22:00"></label>
        
        <label>Rewir / Strefa (np. Parter, Góra): 
          <input type="text" id="wym-new-rewir" placeholder="opcjonalnie, np. Parter" style="width:180px">
        </label>
      </div>
      
      <div style="margin-top: 15px;">
        <button onclick="addWymaganie()" style="background: #10b981;">Dodaj zmianę do zapotrzebowania</button>
      </div>
    </fieldset>
    
    <fieldset style="margin-top: 25px;">
      <legend>📋 Kopiuj cały dzień na zakres dat</legend>
      <div class="row">
        <label>Dzień źródłowy: <input type="date" id="kop-source" value="${today}"></label>
        <label>Cel od: <input type="date" id="kop-start" value="${today}"></label>
        <label>Cel do: <input type="date" id="kop-end" value="${today}"></label>
        <button onclick="kopiujWymagania()" style="background: #3b82f6;">Kopiuj plan zmian</button>
      </div>
    </fieldset>
  `;
  
  loadWymagania();
}

async function loadWymagania() {
  const bocznyZasieg = STATE.wybranyTydzien.split("|");
  const start = bocznyZasieg[0];
  const end   = bocznyZasieg[1];

  const data  = await api(`/wymagania?start=${start}&end=${end}`);
  STATE.wymagania = data;

  const byDate = {};
  for (const w of data) {
    if (!byDate[w.data]) byDate[w.data] = [];
    byDate[w.data].push(w);
  }
  const stanMap = Object.fromEntries(STATE.stanowiska.map(s => [s.id, s]));

  let html = `
    <table style="width:100%; border-collapse: collapse;">
      <thead>
        <tr>
          <th>Data</th>
          <th>Stanowisko / Rewir</th>
          <th>Godziny pracy</th>
          <th>Wymagana liczba osób</th>
          <th>Akcje</th>
        </tr>
      </thead>
      <tbody>`;
      
  const sortedDates = Object.keys(byDate).sort();
  
  if (sortedDates.length === 0) {
    html += `<tr><td colspan="5" style="text-align:center; color:#64748b; padding:20px;">Brak zdefiniowanych wymagań dla wybranego tygodnia.</td></tr>`;
  }

  for (const dt of sortedDates) {
    for (const r of byDate[dt]) {
      const s = stanMap[r.stanowisko_id] || {};
      
      let stanowiskoWyswietlane = s.nazwa || `ID: ${r.stanowisko_id}`;
      if (r.rewir) {
        stanowiskoWyswietlane += ` <span style="color:#2563eb; font-weight:600;">(${r.rewir})</span>`;
      }
      if (s.tylko_weekend) {
        stanowiskoWyswietlane += ` <small style="color:#ef4444; background:#fef2f2; padding:2px 4px; border-radius:4px; font-size:10px; margin-left:5px;">WEEKEND</small>`;
      }

      const g_od = r.godz_od ? r.godz_od.slice(0, 5) : "Brak";
      const g_do = r.godz_do ? r.godz_do.slice(0, 5) : "Brak";
      const godzinyWyswietlane = r.godz_od ? `<span class="badge-time">${g_od} - ${g_do}</span>` : `<span style="color:#94a3b8;">Niezdefiniowane</span>`;

      html += `
        <tr>
          <td><strong>${dt}</strong></td>
          <td>${stanowiskoWyswietlane}</td>
          <td>${godzinyWyswietlane}</td>
          <td style="text-align:center;">
            <input type="number" id="wl-${r.id}" value="${r.liczba_osob}" min="1" style="width:60px; text-align:center;" onchange="updateWymaganieLiczba(${r.id}, this.value)"> os.
          </td>
          <td>
            <button class="danger" onclick="deleteWymaganie(${r.id})" style="padding: 4px 8px; font-size: 12px;">Usuń</button>
          </td>
        </tr>`;
    }
  }
  
  html += "</tbody></table>";
  document.getElementById("wym-table-cont").innerHTML = html;
}

async function addWymaganie() {
  const data          = document.getElementById("wym-new-data").value;
  const stanowisko_id = +document.getElementById("wym-new-stan").value;
  const PlatformLiczba   = +document.getElementById("wym-new-liczba").value;
  
  const raw_od        = document.getElementById("wym-new-od").value;
  const raw_do        = document.getElementById("wym-new-do").value;
  const raw_rewir     = document.getElementById("wym-new-rewir").value.trim();

  const godz_od = raw_od ? `${raw_od}:00` : null;
  const godz_do = raw_do ? `${raw_do}:00` : null;
  const rewir   = raw_rewir ? raw_rewir : null;

  try {
    await api("/wymagania", "POST", { data, stanowisko_id, liczba_osob: PlatformLiczba, godz_od, godz_do, rewir });
    document.getElementById("wym-new-rewir").value = "";
    loadWymagania();
  } catch (e) { alert(e.message); }
}

async function updateWymaganieLiczba(id, nowaLiczba) {
  const istniejące = STATE.wymagania.find(w => w.id === id);
  if (!istniejące) return;
  try {
    await api("/wymagania", "POST", {
      data: istniejące.data,
      stanowisko_id: istniejące.stanowisko_id,
      liczba_osob: +nowaLiczba,
      godz_od: istniejące.godz_od,
      godz_do: istniejące.godz_do,
      rewir: istniejące.rewir
    });
    loadWymagania();
  } catch (e) { alert(e.message); }
}

async function deleteWymaganie(id) {
  try {
    await api(`/wymagania/${id}`, "DELETE");
    loadWymagania();
  } catch (e) { alert(e.message); }
}

async function kopiujWymagania() {
  const source_date = document.getElementById("kop-source").value;
  const start_date  = document.getElementById("kop-start").value;
  const end_date    = document.getElementById("kop-end").value;
  try {
    const res = await api("/wymagania/kopiuj", "POST", { source_date, start_date, end_date });
    alert(`Skopiowano ${res.skopiowano} szablonów zmian na wybrany zakres.`);
    loadWymagania();
  } catch (e) { alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════
// IMPORT DYSPOZYCJI (CSV)
// ══════════════════════════════════════════════════════════════════════════

document.getElementById("csv-upload-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("csv-file");
  if (!fileInput.files.length) return alert("Wybierz plik CSV.");
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const res = await fetch(`${API}/dyspozycje/import-csv`, { method: "POST", body: formData });
  const data = await res.json();

  let html = `<p class="ok">Zapisano: ${data.zapisano} wierszy.</p>`;

  if (data.podglad.length) {
    html += `<h3>Podgląd zaimportowanych danych</h3>
      <table><tr><th>Pracownik</th><th>Data</th><th>Dostępność</th><th>Od</th><th>Do</th></tr>
      ${data.podglad.map(r => `
        <tr>
          <td>${r.pracownik}</td>
          <td>${r.data}</td>
          <td>${r.dostepnosc ? "TAK" : "NIE"}</td>
          <td>${r.od}</td>
          <td>${r.do}</td>
        </tr>`).join("")}
      </table>`;
  }

  if (data.konflikty.length) {
    html += `<h3 class="error">Konflikty / błędy mapowania</h3>
      <table><tr><th>Wiersz</th><th>Problem</th></tr>
      ${data.konflikty.map(k => `
        <tr><td>${k.wiersz}</td><td class="error">${k.problem}</td></tr>`).join("")}
      </table>`;
  }

  document.getElementById("import-preview").innerHTML = html;
});

// ══════════════════════════════════════════════════════════════════════════
// GRAFIK
// ══════════════════════════════════════════════════════════════════════════

async function renderGrafik() {
  const cont = document.getElementById("grafik-content");
  cont.innerHTML = `
    <h2>Interaktywny Grafik Pracy</h2>
    <div class="row" style="background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 20px;">
      <label>Wybierz tydzień grafiku: ${zbudujDropdownTygodni("g-tydzien-sel", "loadGrafik")}</label>
      <button onclick="autoAssign()" style="background: #10b981; font-weight: bold; margin-left:10px;">🤖 Automatycznie przydziel</button>
      <button class="danger" onclick="clearAssignments()">🗑 Wyczyść tydzień</button>
    </div>
    <div id="niedobory-box"></div>
    <div class="scroll-x" id="grafik-table-cont" style="margin-top: 15px;"></div>
  `;
  
  loadGrafik();
}

async function loadGrafik() {
  await loadDicts();
  const bocznyZasieg = STATE.wybranyTydzien.split("|");
  const start = bocznyZasieg[0];
  const end   = bocznyZasieg[1];

  const [przydzialy, dyspozycje, wymagania] = await Promise.all([
    api(`/przydzialy?start=${start}&end=${end}`),
    api(`/dyspozycje?start=${start}&end=${end}`),
    api(`/wymagania?start=${start}&end=${end}`),
  ]);
  
  STATE.przydzialy  = przydzialy;
  STATE.dyspozycje  = dyspozycje;
  STATE.wymagania   = wymagania;

  const dates = [];
  let cur = new Date(start + "T00:00:00");
  const endD = new Date(end + "T00:00:00");
  while (cur <= endD) {
    dates.push(cur.toISOString().slice(0, 10));
    cur.setDate(cur.getDate() + 1);
  }

  const stanMap = Object.fromEntries(STATE.stanowiska.map(s => [s.id, s]));
  
  const przyMap = {};
  for (const a of przydzialy) {
    const key = `${a.data}_${a.pracownik_id}`;
    if (!przyMap[key]) przyMap[key] = [];
    przyMap[key].push(a);
  }
  
  const dysMap = {};
  for (const d of dyspozycje) {
    dysMap[`${d.data}_${d.pracownik_id}`] = d;
  }

  const wymMap = {};
  for (const w of wymagania) {
    if (!wymMap[w.data]) wymMap[w.data] = [];
    wymMap[w.data].push(w);
  }

  const DZIEN = ["Nd","Pn","Wt","Śr","Cz","Pt","Sb"];

  let thead = `<tr><th style="min-width: 200px; max-width: 200px; position: sticky; left: 0; background: #fff; z-index: 10; border-right: 2px solid #e2e8f0;">Pracownik</th>`;
  for (const dt of dates) {
    const d = new Date(dt + "T00:00:00");
    const wd = DZIEN[d.getDay()];
    const isW = d.getDay() === 0 || d.getDay() === 6;
    const cellStyle = isW ? "background: #fef2f2; color: #ef4444; font-weight: bold;" : "";
    thead += `<th style="${cellStyle} min-width: 110px; text-align: center;">${dt.slice(5)}<br><small>${wd}</small></th>`;
  }
  thead += "</tr>";

  let tbody = "";
  for (const p of STATE.pracownicy) {
    tbody += `<tr><td style="position: sticky; left: 0; background: #fff; font-weight: 600; border-right: 2px solid #e2e8f0; z-index: 5; white-space: nowrap;">${p.imie} ${p.nazwisko}</td>`;
    
    for (const dt of dates) {
      const dys = dysMap[`${dt}_${p.id}`];
      const pAt = przyMap[`${dt}_${p.id}`] || [];
      const d = new Date(dt + "T00:00:00");
      const isW = d.getDay() === 0 || d.getDay() === 6;

      const kwalIds = new Set((p.kwalifikacje || []).map(k => k.id));
      const dzisiejszeSzablony = (wymMap[dt] || []).filter(w => {
        const stan = stanMap[w.stanowisko_id];
        if (!stan) return false;
        if (stan.tylko_weekend && !isW) return false;
        return kwalIds.has(w.stanowisko_id);
      });

      let cellBg = "";
      let statusTekst = "";
      
      if (!dys) {
        cellBg = "background-color: #f1f5f9; color: #94a3b8;";
        statusTekst = `<div style="font-size: 10px; color: #94a3b8; text-align:center;">brak dysp.</div>`;
      } else if (!dys.dostepnosc) {
        cellBg = "background-color: #ffe4e6;";
        statusTekst = `<div style="font-size: 10px; color: #be123c; text-align:center; font-weight:600;">X NIE</div>`;
      } else {
        cellBg = "background-color: #f0fdf4;"; 
        if (dys.godz_od || dys.godz_do) {
          const g_od = dys.godz_od ? dys.godz_od.slice(0, 5) : "00:00";
          const g_do = dys.godz_do ? dys.godz_do.slice(0, 5) : "koniec";
          statusTekst = `<div style="font-size: 9px; color: #166534; margin-bottom: 4px; text-align:center; background:#dcfce7; border-radius:4px; padding:1px;">⏱ ${g_od}-${g_do}</div>`;
        }
      }

      let cellHtml = `<td style="${cellBg} padding: 6px; vertical-align: top; border: 1px solid #e2e8f0;">${statusTekst}`;

      for (const a of pAt) {
        const stan = stanMap[a.stanowisko_id] || { nazwa: `ID: ${a.stanowisko_id}` };
        const powiazanySzablon = dzisiejszeSzablony.find(w => w.stanowisko_id === a.stanowisko_id && w.godz_od === a.godz_od);
        const rewirWpisywany = powiazanySzablon && powiazanySzablon.rewir ? ` (${powiazanySzablon.rewir})` : "";

        const g_od = a.godz_od ? a.godz_od.slice(0, 5) : "";
        const g_do = a.godz_do ? a.godz_do.slice(0, 5) : "";
        const godz_str = g_od ? `${g_od}-${g_do}` : "całość";

        cellHtml += `
          <div class="slot-item-assigned" style="background: #ffffff; border: 1px solid #3b82f6; border-radius: 6px; padding: 4px; margin-bottom: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
            <div style="font-weight: 700; font-size: 12px; color: #1e40af;">${stan.nazwa}${rewirWpisywany}</div>
            <div style="font-size: 11px; font-family: monospace; color: #475569; margin: 2px 0;">⏰ ${godz_str}</div>
            
            <select onchange="changeAssignment(${a.id}, this.value, '${dt}', ${p.id})" style="width: 100%; font-size: 10px; padding: 2px; margin-top: 2px;">
              <option value="STAY">— przypisany —</option>
              <option value="REMOVE">❌ Usuń zmianę</option>
            </select>
          </div>`;
      }

      if (pAt.length === 0 && dys && dys.dostepnosc && dzisiejszeSzablony.length > 0) {
        cellHtml += `
          <div class="slot-item-add" style="margin-top: 4px;">
            <select onchange="addAdvancedAssignment(this, '${dt}', ${p.id})" style="width:100%; font-size:11px; padding:3px; background:#fff; border-radius:4px; border:1px solid #cbd5e1; cursor:pointer;">
              <option value="">+ Przydziel</option>
              ${dzisiejszeSzablony.map((w, idx) => {
                const sName = stanMap[w.stanowisko_id]?.nazwa || "Stanowisko";
                const rName = w.rewir ? ` (${w.rewir})` : "";
                const timeStr = w.godz_od ? ` [${w.godz_od.slice(0,5)}-${w.godz_do.slice(0,5)}]` : "";
                return `<option value="${idx}">${sName}${rName}${timeStr}</option>`;
              }).join("")}
            </select>
          </div>`;
      }

      cellHtml += "</td>";
      tbody += cellHtml;
    }
    tbody += "</tr>";
  }

  document.getElementById("grafik-table-cont").innerHTML =
    `<table id="grafik-table" class="modern-grid-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
}

async function addAdvancedAssignment(select, dt, pracId) {
  const idx = select.value;
  if (idx === "") return;
  
  const d = new Date(dt + "T00:00:00");
  const isW = d.getDay() === 0 || d.getDay() === 6;
  
  const wymMap = STATE.wymagania.filter(w => w.data === dt);
  const stanMap = Object.fromEntries(STATE.stanowiska.map(s => [s.id, s]));
  const p = STATE.pracownicy.find(x => x.id === pracId);
  const kwalIds = new Set((p.kwalifikacje || []).map(k => k.id));
  
  const dzisiejszeSzablony = wymMap.filter(w => {
    const stan = stanMap[w.stanowisko_id];
    if (!stan) return false;
    if (stan.tylko_weekend && !isW) return false;
    return kwalIds.has(w.stanowisko_id);
  });

  const wybranySzablon = dzisiejszeSzablony[+idx];
  if (!wybranySzablon) return;

  try {
    await api("/przydzialy", "POST", {
      data: dt,
      stanowisko_id: wybranySzablon.stanowisko_id,
      pracownik_id: pracId,
      godz_od: wybranySzablon.godz_od,
      godz_do: wybranySzablon.godz_do
    });
    loadGrafik();
  } catch (e) {
    alert(e.message);
    select.value = "";
  }
}

async function changeAssignment(aid, action, dt, pracId) {
  if (action === "REMOVE") {
    try {
      await api(`/przydzialy/${aid}`, "DELETE");
      loadGrafik();
    } catch (e) { alert(e.message); }
  } else {
    loadGrafik();
  }
}

async function autoAssign() {
  const bocznyZasieg = STATE.wybranyTydzien.split("|");
  const start = bocznyZasieg[0];
  const end   = bocznyZasieg[1];
  const niedoboryBox = document.getElementById("niedobory-box");
  
  niedoboryBox.innerHTML = '<p style="color: #3b82f6; font-weight:600;">Sztuczna inteligencja analizuje kwalifikacje i godziny z formularzy... Generowanie grafiku.</p>';
  
  try {
    const res = await api(`/auto-assign?start=${start}&end=${end}`, "POST");
    let html = `<div style="background:#dcfce7; border-left:4px solid #10b981; padding:12px; margin-bottom:15px; border-radius:4px;"><p class="ok" style="color:#15803d; font-weight:600; margin:0;">🚀 Sukces! Algorytm automatycznie obsadził: ${res.przydzielone} zmian roboczych.</p></div>`;
    
    if (res.niedobory.length) {
      html += `
        <div style="background:#fff7ed; border:1px solid #fed7aa; padding:15px; border-radius:8px;">
          <h3 class="warn" style="color:#c2410c; margin-top:0;">⚠️ Wykaz nieobsadzonych rewirów / zmian (${res.niedobory.length})</h3>
          <p style="font-size:13px; color:#7c2d12; margin-bottom:8px;">Poniższe zmiany nie zostały obsadzone, ponieważ nikt z uprawnieniami nie zadeklarował zgodnych godzin w Formularzu Google:</p>
          <table style="width:100%; font-size:13px;">
            <tr style="background:#ffedd5;"><th>Data</th><th>Wymagana zmiana (Rewir)</th><th>Status personelu w tym dniu</th></tr>
            ${res.niedobory.map(n =>
              `<tr><td><strong>${n.data}</strong></td><td><span style="color:#b45309; font-weight:600;">${n.stanowisko}</span></td><td style="color:#9a3412; font-size:12px;">${n.powod}</td></tr>`
            ).join("")}
          </table>
        </div>`;
    }
    niedoboryBox.innerHTML = html;
    loadGrafik();
  } catch (e) { alert(e.message); }
}

async function clearAssignments() {
  const bocznyZasieg = STATE.wybranyTydzien.split("|");
  const start = bocznyZasieg[0];
  const end   = bocznyZasieg[1];
  if (!confirm(`Czy na pewno chcesz całkowicie wyczyścić grafik dla wybranego tygodnia (${start} do ${end})?`)) return;
  try {
    await api(`/przydzialy?start=${start}&end=${end}`, "DELETE");
    document.getElementById("niedobory-box").innerHTML = "";
    loadGrafik();
  } catch (e) { alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════
// EKSPORT
// ══════════════════════════════════════════════════════════════════════════

function renderEksport() {
  const cont = document.getElementById("tab-eksport");
  cont.innerHTML = `
    <h2>Eksport grafiku do CSV</h2>
    <fieldset>
      <legend>Wybierz tydzień do pobrania</legend>
      <div class="row">
        <label>Tydzień: ${zbudujDropdownTygodni("eksport-tydzien-sel", "pobierzEksportCSV")}</label>
        <button id="eksport-btn" onclick="pobierzEksportCSV()" style="background: #10b981; margin-left:10px;">Pobierz grafik (CSV)</button>
      </div>
    </fieldset>
  `;
}

function pobierzEksportCSV() {
  const bocznyZasieg = STATE.wybranyTydzien.split("|");
  const start = bocznyZasieg[0];
  const end   = bocznyZasieg[1];
  window.location.href = `${API}/eksport-csv?start=${start}&end=${end}`;
}

// ── init ────────────────────────────────────────────────────────────────
document.querySelector("nav button").click();