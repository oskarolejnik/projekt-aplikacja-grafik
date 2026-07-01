// Parsowanie kwoty z pola tekstowego, tolerujące polski separator dziesiętny (przecinek).
// Bez tego parseFloat('1234,56') urywa się na przecinku i zwraca 1234 — cicha utrata groszy
// w rozliczeniach i zeszycie kasowym (błąd propagował na saldo narastająco).
export const num = (v) => (v === '' || v == null ? 0 : parseFloat(String(v).replace(',', '.')) || 0)
