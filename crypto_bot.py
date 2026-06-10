"""
╔══════════════════════════════════════════════════════════════╗
║         🤖 CRYPTO BOT TELEGRAM — Solo Notifiche              ║
╠══════════════════════════════════════════════════════════════╣
║  CRYPTO: BTC · ETH · SOL · BNB · XRP · ADA · AVAX · DOGE   ║
║                                                              ║
║  REGOLE INGRESSO (tutte e tre devono essere vere):           ║
║    1. RSI(14) < 32                                           ║
║    2. MACD crossover rialzista                               ║
║    3. Volume +25% rispetto alla media delle ultime 6 candele ║
║                                                              ║
║  REGOLE USCITA:                                              ║
║    • +8%   → avviso Take Profit                              ║
║    • +15%  → avviso Take Profit Aggressivo                   ║
║    • -4%   → avviso Stop Loss                                ║
║    • -6%   → avviso Stop Loss Duro                           ║
╠══════════════════════════════════════════════════════════════╣
║  INSTALLAZIONE:  pip install requests                        ║
║  AVVIO:          python crypto_bot.py                        ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import time
import json
import os
from datetime import datetime, timezone, timedelta

FUSO_ITALIA = timezone(timedelta(hours=2))  # CEST (UTC+2 — ora italiana)
def adesso_italia():
    """Ora italiana corrente (UTC+2)."""
    return datetime.now(FUSO_ITALIA)

# ================================================================
# ⚙️  CONFIGURAZIONE — MODIFICA QUESTI VALORI PRIMA DI AVVIARE
# ================================================================
TELEGRAM_BOT_TOKEN = "8902440129:AAEhVmHw1964uebB1WKqhTwbvBrs1Yx79eo""
TELEGRAM_CHAT_ID   = "5308622892"

# Crypto da monitorare — id CoinGecko → nome visualizzato
CRYPTOS = {
    "bitcoin":     "Bitcoin  (BTC)",
    "ethereum":    "Ethereum (ETH)",
    "solana":      "Solana   (SOL)",
    "binancecoin": "BNB      (BNB)",
    "ripple":      "XRP      (XRP)",
    "cardano":     "Cardano  (ADA)",
    "avalanche-2": "Avalanche(AVAX)",
    "dogecoin":    "Dogecoin (DOGE)",
}

CONTROLLA_OGNI_MINUTI = 15   # frequenza controllo mercati
REPORT_ORA            = 9    # ora del report giornaliero (formato 24h)
FILE_STATO            = "stato_bot.json"

# --- Regole di ingresso ---------------------------------------------
RSI_SOGLIA        = 32    # RSI sotto questo valore → possibile ingresso
VOLUME_AUMENTO    = 25    # volume deve essere +N% sopra la media
VOLUME_CANDELE    = 6     # media volume calcolata su N candele

# --- Regole di uscita (% rispetto al prezzo di entrata) -------------
TP_PCT        =  8.0   # avviso Take Profit
TP_AGGR_PCT   = 15.0   # avviso Take Profit Aggressivo
SL_PCT        = -4.0   # avviso Stop Loss
SL_DURO_PCT   = -6.0   # avviso Stop Loss Duro
# ================================================================


# ────────────────────────────────────────────────────────────────
# TELEGRAM
# ────────────────────────────────────────────────────────────────

def invia_messaggio(testo: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       testo,
            "parse_mode": "HTML",
        }, timeout=10)
        if not r.ok:
            print(f"  [Telegram] Errore: {r.status_code} — {r.text[:60]}")
    except Exception as e:
        print(f"  [Telegram] {e}")


# ────────────────────────────────────────────────────────────────
# STATO (posizioni aperte salvate su file)
# ────────────────────────────────────────────────────────────────

def carica_stato() -> dict:
    if os.path.exists(FILE_STATO):
        try:
            with open(FILE_STATO, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"posizioni": {}}

def salva_stato(stato: dict) -> None:
    with open(FILE_STATO, "w") as f:
        json.dump(stato, f, indent=2, ensure_ascii=False)

def in_posizione(stato: dict, crypto_id: str) -> bool:
    return stato["posizioni"].get(crypto_id, {}).get("in_posizione", False)

def apri_posizione(stato: dict, crypto_id: str, prezzo: float) -> None:
    stato["posizioni"][crypto_id] = {
        "in_posizione":    True,
        "prezzo_entrata":  prezzo,
        "ora_entrata":     adesso_italia().strftime("%d/%m/%Y %H:%M"),
        "tp_colpito":      False,
        "aggr_tp_colpito": False,
        "sl_colpito":      False,
        "sl_duro_colpito": False,
    }
    salva_stato(stato)

def chiudi_posizione(stato: dict, crypto_id: str) -> None:
    if crypto_id in stato["posizioni"]:
        stato["posizioni"][crypto_id]["in_posizione"] = False
    salva_stato(stato)


# ────────────────────────────────────────────────────────────────
# DATI DI MERCATO — CoinGecko (gratuito, no API key)
# ────────────────────────────────────────────────────────────────

def ottieni_dati(crypto_id: str, giorni: int = 3) -> tuple[list, list]:
    """Ritorna (prezzi, volumi) orari degli ultimi N giorni.
    Gestisce il rate limit di CoinGecko con pausa e retry."""
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart"
    for tentativo in range(3):
        try:
            time.sleep(2)
            r = requests.get(url, params={
                "vs_currency": "eur",
                "days":        giorni,
                "interval":    "hourly",
            }, timeout=15)
            if r.status_code == 429:
                attesa = 20 * (tentativo + 1)
                print(f"  [CoinGecko] Rate limit su {crypto_id} — attendo {attesa}s")
                time.sleep(attesa)
                continue
            dati   = r.json()
            prezzi = [p[1] for p in dati.get("prices", [])]
            volumi = [v[1] for v in dati.get("total_volumes", [])]
            if prezzi:
                return prezzi, volumi
        except Exception as e:
            print(f"  [CoinGecko] {crypto_id} (tentativo {tentativo+1}): {e}")
            time.sleep(5)
    return [], []


# ────────────────────────────────────────────────────────────────
# PREZZI IN TEMPO REALE (una sola richiesta per tutte le crypto)
# ────────────────────────────────────────────────────────────────

def get_prezzi_correnti() -> dict:
    """Ritorna i prezzi attuali di tutte le crypto in una sola richiesta.
    Molto più veloce e preciso rispetto ai dati storici per il report."""
    ids = ",".join(CRYPTOS.keys())
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "eur"},
            timeout=10,
        )
        # Risultato: {"bitcoin": {"eur": 52959.96}, "ethereum": {"eur": 1401.46}, ...}
        return {cid: dati.get("eur", 0) for cid, dati in r.json().items()}
    except Exception as e:
        print(f"  [CoinGecko/prezzi] {e}")
        return {}


# ────────────────────────────────────────────────────────────────
# INDICATORI TECNICI
# ────────────────────────────────────────────────────────────────

def ema_serie(prezzi: list[float], periodo: int) -> list[float]:
    if len(prezzi) < periodo:
        return []
    mult  = 2 / (periodo + 1)
    serie = [sum(prezzi[:periodo]) / periodo]
    for p in prezzi[periodo:]:
        serie.append((p - serie[-1]) * mult + serie[-1])
    return serie

def calcola_rsi(prezzi: list[float], periodo: int = 14) -> float | None:
    if len(prezzi) < periodo + 1:
        return None
    g, l = [], []
    for i in range(1, len(prezzi)):
        d = prezzi[i] - prezzi[i - 1]
        g.append(max(d, 0.0))
        l.append(max(-d, 0.0))
    mg = sum(g[-periodo:]) / periodo
    ml = sum(l[-periodo:]) / periodo
    if ml == 0:
        return 100.0
    return round(100 - 100 / (1 + mg / ml), 2)

def calcola_macd(prezzi: list[float]) -> dict | None:
    e12 = ema_serie(prezzi, 12)
    e26 = ema_serie(prezzi, 26)
    if not e12 or not e26:
        return None
    off   = len(e12) - len(e26)
    linea = [e12[i + off] - e26[i] for i in range(len(e26))]
    seg   = ema_serie(linea, 9)
    if len(seg) < 2:
        return None
    crossover = linea[-2] < seg[-2] and linea[-1] > seg[-1]
    return {
        "macd":      round(linea[-1], 6),
        "segnale":   round(seg[-1], 6),
        "crossover": crossover,
    }

def check_volume(volumi: list[float], n: int, pct: float) -> tuple[bool, float, float]:
    if len(volumi) < n + 1:
        return False, 0.0, 0.0
    v = volumi[-1]
    m = sum(volumi[-(n + 1):-1]) / n
    return v >= m * (1 + pct / 100), v, m


# ────────────────────────────────────────────────────────────────
# FORMATTAZIONE
# ────────────────────────────────────────────────────────────────

def fmt_prezzo(v: float) -> str:
    if v >= 1000: return f"€{v:,.2f}"
    if v >= 1:    return f"€{v:.4f}"
    return f"€{v:.6f}"

def fmt_vol(v: float) -> str:
    if v >= 1e9: return f"€{v/1e9:.2f}B"
    if v >= 1e6: return f"€{v/1e6:.2f}M"
    return f"€{v:,.0f}"


# ────────────────────────────────────────────────────────────────
# MESSAGGI
# ────────────────────────────────────────────────────────────────

def msg_compra(name, prezzo, rsi, rsi_ok, macd_ok, v_ok, vp, vol_att, vol_media) -> str:
    tp  = prezzo * (1 + TP_PCT      / 100)
    atp = prezzo * (1 + TP_AGGR_PCT / 100)
    sl  = prezzo * (1 + SL_PCT      / 100)
    hsl = prezzo * (1 + SL_DURO_PCT / 100)
    n_ok = sum([rsi_ok, macd_ok, v_ok])
    forza = "🔥 Forte" if n_ok == 3 else "⚡ Medio"
    return (
        f"🟢 <b>SEGNALE COMPRA — {name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Prezzo: {fmt_prezzo(prezzo)}\n"
        f"📲 <b>Compra sulla tua piattaforma</b>\n"
        f"📶 Segnale: {forza} ({n_ok}/3 condizioni)\n\n"
        f"<b>📊 Indicatori</b>\n"
        f"  RSI(14)  : {rsi}  {'✅' if rsi_ok else '❌'} &lt; {RSI_SOGLIA}\n"
        f"  MACD     : {'crossover rialzista ✅' if macd_ok else 'nessun crossover ❌'}\n"
        f"  Volume   : {'+' if vp>=0 else ''}{vp:.1f}% {'✅' if v_ok else '❌'}  (media {fmt_vol(vol_media)})\n\n"
        f"<b>🎯 Livelli da monitorare</b>\n"
        f"  TP       : {fmt_prezzo(tp)}  (+{TP_PCT}%)\n"
        f"  TP Aggr. : {fmt_prezzo(atp)} (+{TP_AGGR_PCT}%)\n"
        f"  SL       : {fmt_prezzo(sl)}  ({SL_PCT}%)\n"
        f"  SL Duro  : {fmt_prezzo(hsl)} ({SL_DURO_PCT}%)\n\n"
        f"⚠️ <i>Segnale algoritmico — non è consulenza finanziaria.</i>\n"
        f"🕐 {adesso_italia().strftime('%d/%m/%Y %H:%M')}"
    )

def msg_uscita(name, p_att, p_ent, tipo, pct) -> str:
    tabella = {
        "TP":       ("💰", f"TAKE PROFIT +{TP_PCT}%",
                     "Valuta se vendere o tenere la posizione"),
        "TP_AGGR":  ("🚀", f"TP AGGRESSIVO +{TP_AGGR_PCT}%",
                     "Ottimo momento per vendere sulla tua piattaforma"),
        "SL":       ("⚠️", f"STOP LOSS {SL_PCT}%",
                     "Valuta se uscire o tenere la posizione"),
        "SL_DURO":  ("🛑", f"STOP LOSS DURO {SL_DURO_PCT}%",
                     "Considera di vendere subito sulla tua piattaforma"),
    }
    emoji, titolo, azione = tabella[tipo]
    segno = "+" if pct >= 0 else ""
    return (
        f"{emoji} <b>{name} — {titolo}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Prezzo attuale : {fmt_prezzo(p_att)}\n"
        f"📌 Prezzo entrata : {fmt_prezzo(p_ent)}\n"
        f"📈 Variazione     : {segno}{pct:.2f}%\n"
        f"🔔 {azione}\n\n"
        f"⚠️ <i>Segnale algoritmico — non è consulenza finanziaria.</i>\n"
        f"🕐 {adesso_italia().strftime('%d/%m/%Y %H:%M')}"
    )


# ────────────────────────────────────────────────────────────────
# LOGICA INGRESSO
# ────────────────────────────────────────────────────────────────

def controlla_ingressi(stato: dict) -> None:
    for crypto_id, name in CRYPTOS.items():
        if in_posizione(stato, crypto_id):
            continue

        prezzi, volumi = ottieni_dati(crypto_id, giorni=3)
        if len(prezzi) < 50:
            print(f"  [{name}] Dati insufficienti — skip")
            continue

        rsi  = calcola_rsi(prezzi)
        macd = calcola_macd(prezzi)
        v_ok, v_att, v_med = check_volume(volumi, VOLUME_CANDELE, VOLUME_AUMENTO)

        if rsi is None or macd is None:
            continue

        rsi_ok  = rsi < RSI_SOGLIA
        macd_ok = macd["crossover"]
        prezzo  = prezzi[-1]
        vp      = (v_att / v_med - 1) * 100 if v_med else 0

        print(
            f"  [{name}] {fmt_prezzo(prezzo)} | "
            f"RSI {rsi} {'✅' if rsi_ok else '❌'} | "
            f"MACD {'✅' if macd_ok else '❌'} | "
            f"Vol {'+' if vp>=0 else ''}{vp:.1f}% {'✅' if v_ok else '❌'}"
        )

        condizioni_ok = sum([rsi_ok, macd_ok, v_ok])  # quante condizioni sono vere
        if condizioni_ok >= 2:
            print(f"  🟢 SEGNALE COMPRA su {name}! ({condizioni_ok}/3 condizioni)")
            invia_messaggio(msg_compra(name, prezzo, rsi, rsi_ok,
                                       macd_ok, v_ok, vp, v_att, v_med))
            apri_posizione(stato, crypto_id, prezzo)


# ────────────────────────────────────────────────────────────────
# LOGICA USCITA
# ────────────────────────────────────────────────────────────────

def controlla_uscite(stato: dict) -> None:
    for crypto_id, name in CRYPTOS.items():
        if not in_posizione(stato, crypto_id):
            continue

        pos   = stato["posizioni"][crypto_id]
        p_ent = pos["prezzo_entrata"]

        prezzi, _ = ottieni_dati(crypto_id, giorni=1)
        if not prezzi:
            continue
        p_att = prezzi[-1]
        pct   = (p_att / p_ent - 1) * 100
        segno = "+" if pct >= 0 else ""

        print(
            f"  [{name}] Entrata {fmt_prezzo(p_ent)} → "
            f"Ora {fmt_prezzo(p_att)} ({segno}{pct:.2f}%)"
        )

        # TP Aggressivo (+15%) → avviso e chiudi
        if pct >= TP_AGGR_PCT and not pos.get("aggr_tp_colpito"):
            invia_messaggio(msg_uscita(name, p_att, p_ent, "TP_AGGR", pct))
            pos["aggr_tp_colpito"] = True
            pos["tp_colpito"]      = True
            chiudi_posizione(stato, crypto_id)
            print(f"  🚀 TP Aggressivo — posizione chiusa")

        # TP normale (+8%) → avviso, lascia correre
        elif pct >= TP_PCT and not pos.get("tp_colpito"):
            invia_messaggio(msg_uscita(name, p_att, p_ent, "TP", pct))
            pos["tp_colpito"] = True
            salva_stato(stato)
            print(f"  💰 TP — avviso inviato, posizione aperta")

        # SL Duro (-6%) → avviso e chiudi
        elif pct <= SL_DURO_PCT and not pos.get("sl_duro_colpito"):
            invia_messaggio(msg_uscita(name, p_att, p_ent, "SL_DURO", pct))
            pos["sl_duro_colpito"] = True
            chiudi_posizione(stato, crypto_id)
            print(f"  🛑 SL Duro — posizione chiusa")

        # SL avviso (-4%) → avviso, lascia correre
        elif pct <= SL_PCT and not pos.get("sl_colpito"):
            invia_messaggio(msg_uscita(name, p_att, p_ent, "SL", pct))
            pos["sl_colpito"] = True
            salva_stato(stato)
            print(f"  ⚠️ SL — avviso inviato")


# ────────────────────────────────────────────────────────────────
# REPORT GIORNALIERO
# ────────────────────────────────────────────────────────────────

def report_giornaliero(stato: dict) -> None:
    prezzi_ora = get_prezzi_correnti()  # tutti i prezzi in una sola richiesta
    righe = ["📊 <b>REPORT GIORNALIERO</b>\n"]
    for crypto_id, name in CRYPTOS.items():
        prezzo = prezzi_ora.get(crypto_id, 0)
        if not prezzo:
            righe.append(f"⚪ <b>{name}</b>  — dati non disponibili")
            continue
        pos    = stato["posizioni"].get(crypto_id, {})
        aperta = pos.get("in_posizione", False)
        if aperta:
            p_ent = pos["prezzo_entrata"]
            pct   = (prezzo / p_ent - 1) * 100
            emoji = "🟢" if pct >= 0 else "🔴"
            righe.append(
                f"{emoji} <b>{name}</b>  {fmt_prezzo(prezzo)}\n"
                f"   In posizione: {'+' if pct>=0 else ''}{pct:.2f}% "
                f"(entrata {fmt_prezzo(p_ent)})"
            )
        else:
            righe.append(f"⚪ <b>{name}</b>  {fmt_prezzo(prezzo)}")
    righe.append(f"\n🕐 {adesso_italia().strftime('%d/%m/%Y %H:%M')}")
    invia_messaggio("\n\n".join(righe))


# ────────────────────────────────────────────────────────────────
# COMANDI TELEGRAM (polling)
# ────────────────────────────────────────────────────────────────

# Comandi disponibili:
#   /stato     → RSI, MACD e Volume attuali per tutte le crypto
#   /posizioni → posizioni aperte con guadagno/perdita
#   /prezzi    → prezzi aggiornati di tutte le crypto
#   /aiuto     → lista comandi

_ultimo_update_id = 0   # evita di processare lo stesso messaggio due volte

def get_aggiornamenti() -> list[dict]:
    """Recupera i messaggi/comandi inviati al bot."""
    global _ultimo_update_id
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"offset": _ultimo_update_id + 1, "timeout": 2},
            timeout=10,
        )
        updates = r.json().get("result", [])
        if updates:
            _ultimo_update_id = updates[-1]["update_id"]
        return updates
    except Exception:
        return []

def cmd_stato() -> str:
    """RSI e condizioni attuali per tutte le crypto."""
    prezzi_ora = get_prezzi_correnti()  # prezzi in tempo reale
    righe = ["📊 <b>STATO MERCATI</b>\n"]
    for crypto_id, name in CRYPTOS.items():
        prezzi, volumi = ottieni_dati(crypto_id, giorni=3)
        if len(prezzi) < 50:
            righe.append(f"⚪ <b>{name}</b> — dati non disponibili")
            continue
        rsi    = calcola_rsi(prezzi)
        macd   = calcola_macd(prezzi)
        v_ok, v_att, v_med = check_volume(volumi, VOLUME_CANDELE, VOLUME_AUMENTO)
        # Usa prezzo real-time se disponibile, altrimenti ultima candela
        prezzo = prezzi_ora.get(crypto_id) or prezzi[-1]
        vp     = (v_att / v_med - 1) * 100 if v_med else 0

        rsi_ok  = rsi is not None and rsi < RSI_SOGLIA
        macd_ok = macd is not None and macd["crossover"]
        n_ok    = sum([rsi_ok, macd_ok, v_ok])
        emoji   = "🟢" if n_ok >= 2 else ("🟡" if n_ok == 1 else "⚪")

        righe.append(
            f"{emoji} <b>{name}</b>  {fmt_prezzo(prezzo)}\n"
            f"   RSI {rsi} {'✅' if rsi_ok else '❌'}  "
            f"MACD {'✅' if macd_ok else '❌'}  "
            f"Vol {'+' if vp>=0 else ''}{vp:.1f}% {'✅' if v_ok else '❌'}"
        )
    righe.append(f"\n🕐 {adesso_italia().strftime('%d/%m/%Y %H:%M')}")
    return "\n\n".join(righe)

def cmd_posizioni(stato: dict) -> str:
    """Posizioni aperte con P&L attuale."""
    aperte = [(cid, p) for cid, p in stato["posizioni"].items()
              if p.get("in_posizione")]
    if not aperte:
        return "📌 <b>Nessuna posizione aperta al momento.</b>"
    righe = [f"📌 <b>POSIZIONI APERTE ({len(aperte)})</b>\n"]
    for cid, pos in aperte:
        name  = CRYPTOS.get(cid, cid)
        pz, _ = ottieni_dati(cid, giorni=1)
        if not pz:
            continue
        p_att = pz[-1]
        p_ent = pos["prezzo_entrata"]
        pct   = (p_att / p_ent - 1) * 100
        emoji = "🟢" if pct >= 0 else "🔴"
        segno = "+" if pct >= 0 else ""
        righe.append(
            f"{emoji} <b>{name}</b>\n"
            f"   Entrata : {fmt_prezzo(p_ent)}\n"
            f"   Ora     : {fmt_prezzo(p_att)}\n"
            f"   P&L     : {segno}{pct:.2f}%\n"
            f"   Aperta  : {pos.get('ora_entrata', '—')}"
        )
    righe.append(f"\n🕐 {adesso_italia().strftime('%d/%m/%Y %H:%M')}")
    return "\n\n".join(righe)

def cmd_prezzi() -> str:
    """Prezzi aggiornati di tutte le crypto in tempo reale."""
    prezzi_ora = get_prezzi_correnti()
    righe = ["💰 <b>PREZZI IN TEMPO REALE</b>\n"]
    for crypto_id, name in CRYPTOS.items():
        prezzo = prezzi_ora.get(crypto_id, 0)
        if prezzo:
            righe.append(f"  <b>{name}</b>  {fmt_prezzo(prezzo)}")
        else:
            righe.append(f"  <b>{name}</b>  —")
    righe.append(f"\n🕐 {adesso_italia().strftime('%d/%m/%Y %H:%M')}")
    return "\n".join(righe)

def cmd_aiuto() -> str:
    return (
        "🤖 <b>Comandi disponibili</b>\n\n"
        "/stato      — RSI, MACD e Volume di tutte le crypto\n"
        "/posizioni  — Posizioni aperte con guadagno/perdita\n"
        "/prezzi     — Prezzi aggiornati di tutte le 8 crypto\n"
        "/aiuto      — Mostra questa lista\n\n"
        f"⏱ Controllo automatico ogni {CONTROLLA_OGNI_MINUTI} minuti\n"
        f"📊 Report giornaliero alle {REPORT_ORA}:00"
    )

def gestisci_comandi(stato: dict) -> None:
    """Controlla se sono arrivati comandi e risponde."""
    updates = get_aggiornamenti()
    for upd in updates:
        msg  = upd.get("message", {})
        text = msg.get("text", "").strip().lower()
        if not text.startswith("/"):
            continue
        comando = text.split()[0]
        print(f"  [Comando] ricevuto: {comando}")
        if comando == "/stato":
            invia_messaggio(cmd_stato())
        elif comando == "/posizioni":
            invia_messaggio(cmd_posizioni(stato))
        elif comando == "/prezzi":
            invia_messaggio(cmd_prezzi())
        elif comando == "/aiuto":
            invia_messaggio(cmd_aiuto())
        else:
            invia_messaggio(
                f"❓ Comando non riconosciuto: <code>{comando}</code>\n"
                "Scrivi /aiuto per vedere i comandi disponibili."
            )


# ────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────

def main() -> None:
    print("╔══════════════════════════════════════════════╗")
    print("║     🤖 CRYPTO BOT TELEGRAM — Avviato         ║")
    print(f"║     Crypto monitorate: {len(CRYPTOS)}                  ║")
    print(f"║     Controllo ogni {CONTROLLA_OGNI_MINUTI} minuti               ║")
    print("╚══════════════════════════════════════════════╝\n")

    stato = carica_stato()

    invia_messaggio(
        f"🤖 <b>Crypto Bot Avviato!</b>\n\n"
        f"<b>📈 Crypto monitorate ({len(CRYPTOS)}):</b>\n"
        f"  BTC · ETH · SOL · BNB · XRP · ADA · AVAX · DOGE\n\n"
        f"<b>Regole ingresso (2/3 condizioni):</b>\n"
        f"  • RSI(14) &lt; {RSI_SOGLIA}\n"
        f"  • MACD crossover rialzista\n"
        f"  • Volume +{VOLUME_AUMENTO}% vs media {VOLUME_CANDELE} candele\n\n"
        f"<b>Regole uscita:</b>\n"
        f"  • +{TP_PCT}%  → avviso TP\n"
        f"  • +{TP_AGGR_PCT}% → avviso TP Aggressivo\n"
        f"  • {SL_PCT}%  → avviso SL\n"
        f"  • {SL_DURO_PCT}%  → avviso SL Duro\n\n"
        f"<b>📲 Comandi disponibili:</b>\n"
        f"  /stato · /posizioni · /prezzi · /aiuto\n\n"
        f"⚠️ <i>Segnali algoritmici — non è consulenza finanziaria.</i>"
    )

    ultimo_report_ora  = -1
    ultimo_analisi_min = -1   # minuto dell'ultima analisi di mercato

    while True:
        adesso = adesso_italia()

        # ── Comandi Telegram: controlla ogni minuto ──────────────
        try:
            gestisci_comandi(stato)
        except Exception as e:
            print(f"  [Comandi] {e}")

        # ── Analisi di mercato: ogni CONTROLLA_OGNI_MINUTI minuti
        minuti_trascorsi = adesso.hour * 60 + adesso.minute
        if minuti_trascorsi != ultimo_analisi_min and minuti_trascorsi % CONTROLLA_OGNI_MINUTI == 0:
            print(f"\n[{adesso.strftime('%H:%M:%S')}] ── Analisi mercati ──")
            try:
                controlla_ingressi(stato)
                controlla_uscite(stato)
            except Exception as e:
                print(f"  [ERRORE] {e}")
            ultimo_analisi_min = minuti_trascorsi

        # ── Report giornaliero: esatto all'ora impostata ─────────
        if adesso.hour == REPORT_ORA and adesso.minute == 0 and adesso.hour != ultimo_report_ora:
            try:
                report_giornaliero(stato)
                ultimo_report_ora = adesso.hour
                print(f"  → Report giornaliero inviato alle {REPORT_ORA}:00")
            except Exception as e:
                print(f"  [Report] {e}")

        time.sleep(60)  # controlla ogni minuto


if __name__ == "__main__":
    main()
