"""
╔══════════════════════════════════════════════════════════════╗
║          🤖 CRYPTO BOT TELEGRAM — Versione Avanzata          ║
╠══════════════════════════════════════════════════════════════╣
║  REGOLE DI INGRESSO (devono essere TUTTE e TRE vere):        ║
║    1. RSI(14) < 32                                           ║
║    2. MACD crossover rialzista                               ║
║    3. Volume +25% rispetto alla media delle ultime 6 candele ║
╠══════════════════════════════════════════════════════════════╣
║  REGOLE DI USCITA (monitoraggio continuo):                   ║
║    • Take Profit (TP)           : +8%                        ║
║    • Take Profit Aggressivo     : +15%                       ║
║    • Stop Loss (SL)             : -4%  (avviso)              ║
║    • Stop Loss Duro (Hard SL)   : -6%  (chiudi posizione)    ║
╠══════════════════════════════════════════════════════════════╣
║  INSTALLAZIONE:  pip install requests                        ║
║  AVVIO:          python crypto_bot.py                        ║
╚══════════════════════════════════════════════════════════════╝
"""

import requests
import time
import json
import os
from datetime import datetime

# ================================================================
# ⚙️  CONFIGURAZIONE — MODIFICA QUESTI VALORI PRIMA DI AVVIARE
# ================================================================
TELEGRAM_BOT_TOKEN = "8902440129:AAEhVmHw1964uebB1WKqhTwbvBrs1Yx79eo"    # da @BotFather
TELEGRAM_CHAT_ID   = "5308622892"  # vedi GUIDA.md

CRYPTOS = {
    "bitcoin":  "BTC",
    "ethereum": "ETH",
}

CONTROLLA_OGNI_MINUTI       = 15   # frequenza controllo mercati
AGGIORNAMENTO_GIORNALIERO_ORA = 9  # ora del report giornaliero (formato 24h)
FILE_STATO                  = "stato_bot.json"  # file per salvare posizioni aperte

# --- Regole di ingresso -----------------------------------------
RSI_PERIODO         = 14   # periodo RSI standard
RSI_SOGLIA          = 32   # RSI deve essere SOTTO questa soglia
VOLUME_AUMENTO_PCT  = 25   # volume deve essere N% sopra la media
VOLUME_CANDELE      = 6    # media volume calcolata su N candele

# --- Regole di uscita (percentuali rispetto al prezzo di entrata)
TAKE_PROFIT_PCT     =  8.0   # +8%  → Take Profit normale
AGGR_TP_PCT         = 15.0   # +15% → Take Profit aggressivo
STOP_LOSS_PCT       = -4.0   # -4%  → Stop Loss (avviso)
HARD_STOP_LOSS_PCT  = -6.0   # -6%  → Stop Loss duro (chiudi tutto)
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
            print(f"  [Telegram] Errore: {r.status_code} {r.text[:80]}")
    except Exception as e:
        print(f"  [Telegram] Errore invio: {e}")


# ────────────────────────────────────────────────────────────────
# STATO (posizioni aperte, livelli TP/SL già raggiunti)
# ────────────────────────────────────────────────────────────────

STATO_DEFAULT = {
    "posizioni": {}
    # Struttura per ogni crypto:
    # "BTC": {
    #     "in_posizione":    True,
    #     "prezzo_entrata":  58000.0,
    #     "ora_entrata":     "2024-01-15 09:30",
    #     "tp_colpito":      False,
    #     "aggr_tp_colpito": False,
    #     "sl_colpito":      False,
    # }
}


def carica_stato() -> dict:
    if os.path.exists(FILE_STATO):
        try:
            with open(FILE_STATO, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return json.loads(json.dumps(STATO_DEFAULT))  # deep copy


def salva_stato(stato: dict) -> None:
    with open(FILE_STATO, "w") as f:
        json.dump(stato, f, indent=2)


def posizione_aperta(stato: dict, simbolo: str) -> bool:
    return stato["posizioni"].get(simbolo, {}).get("in_posizione", False)


def apri_posizione(stato: dict, simbolo: str, prezzo: float) -> None:
    stato["posizioni"][simbolo] = {
        "in_posizione":    True,
        "prezzo_entrata":  prezzo,
        "ora_entrata":     datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tp_colpito":      False,
        "aggr_tp_colpito": False,
        "sl_colpito":      False,
    }
    salva_stato(stato)


def chiudi_posizione(stato: dict, simbolo: str) -> None:
    if simbolo in stato["posizioni"]:
        stato["posizioni"][simbolo]["in_posizione"] = False
    salva_stato(stato)


# ────────────────────────────────────────────────────────────────
# DATI DI MERCATO (CoinGecko — gratuito, no API key)
# ────────────────────────────────────────────────────────────────

def ottieni_dati_orari(crypto_id: str, giorni: int = 7) -> tuple[list, list]:
    """
    Restituisce (prezzi, volumi) come liste di float.
    Ogni elemento = 1 candela oraria.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart"
    try:
        r = requests.get(url, params={
            "vs_currency": "eur",
            "days":        giorni,
            "interval":    "hourly",
        }, timeout=15)
        dati    = r.json()
        prezzi  = [p[1] for p in dati.get("prices", [])]
        volumi  = [v[1] for v in dati.get("total_volumes", [])]
        return prezzi, volumi
    except Exception as e:
        print(f"  [API] Errore {crypto_id}: {e}")
        return [], []


# ────────────────────────────────────────────────────────────────
# INDICATORI TECNICI
# ────────────────────────────────────────────────────────────────

def calcola_ema_serie(prezzi: list[float], periodo: int) -> list[float]:
    """EMA completa su tutta la serie."""
    if len(prezzi) < periodo:
        return []
    moltiplicatore = 2 / (periodo + 1)
    ema = [sum(prezzi[:periodo]) / periodo]  # primo valore = SMA
    for p in prezzi[periodo:]:
        ema.append((p - ema[-1]) * moltiplicatore + ema[-1])
    return ema


def calcola_rsi(prezzi: list[float], periodo: int = 14) -> float | None:
    """RSI classico di Wilder."""
    if len(prezzi) < periodo + 1:
        return None
    guadagni, perdite = [], []
    for i in range(1, len(prezzi)):
        delta = prezzi[i] - prezzi[i - 1]
        guadagni.append(max(delta, 0.0))
        perdite.append(max(-delta, 0.0))
    mg = sum(guadagni[-periodo:]) / periodo
    mp = sum(perdite[-periodo:]) / periodo
    if mp == 0:
        return 100.0
    return round(100 - 100 / (1 + mg / mp), 2)


def calcola_macd(prezzi: list[float]) -> dict | None:
    """
    Restituisce un dizionario con:
      macd_attuale, segnale_attuale,
      macd_prec,    segnale_prec,
      crossover_rialzista (bool)
    """
    ema12 = calcola_ema_serie(prezzi, 12)
    ema26 = calcola_ema_serie(prezzi, 26)
    if not ema12 or not ema26:
        return None

    # Allinea le due serie (ema26 è più corta di 14 elementi)
    offset   = len(ema12) - len(ema26)
    linea    = [ema12[i + offset] - ema26[i] for i in range(len(ema26))]

    segnale = calcola_ema_serie(linea, 9)
    if len(segnale) < 2:
        return None

    # Allinea linea MACD con serie segnale
    off2         = len(linea) - len(segnale)
    macd_att     = linea[-1]
    macd_prec    = linea[-2]
    segnale_att  = segnale[-1]
    segnale_prec = segnale[-2]

    crossover = (macd_prec < segnale_prec) and (macd_att > segnale_att)

    return {
        "macd":              round(macd_att, 4),
        "segnale":           round(segnale_att, 4),
        "macd_prec":         round(macd_prec, 4),
        "segnale_prec":      round(segnale_prec, 4),
        "crossover_rialzista": crossover,
    }


def controlla_volume(volumi: list[float], n_candele: int, aumento_pct: float) -> tuple[bool, float, float]:
    """
    Confronta l'ultimo volume con la media delle N candele precedenti.
    Restituisce (condizione_ok, volume_attuale, media_volume).
    """
    if len(volumi) < n_candele + 1:
        return False, 0.0, 0.0
    vol_att  = volumi[-1]
    media    = sum(volumi[-(n_candele + 1):-1]) / n_candele
    soglia   = media * (1 + aumento_pct / 100)
    return vol_att >= soglia, vol_att, media


# ────────────────────────────────────────────────────────────────
# MESSAGGI TELEGRAM
# ────────────────────────────────────────────────────────────────

def fmt_eur(v: float) -> str:
    if v >= 1000:
        return f"€{v:,.2f}"
    elif v >= 1:
        return f"€{v:.4f}"
    return f"€{v:.6f}"


def fmt_vol(v: float) -> str:
    if v >= 1_000_000_000:
        return f"€{v/1_000_000_000:.2f}B"
    elif v >= 1_000_000:
        return f"€{v/1_000_000:.2f}M"
    return f"€{v:,.0f}"


def msg_ingresso(simbolo: str, prezzo: float, rsi: float, macd: dict,
                 vol_att: float, vol_media: float) -> str:
    vol_pct = (vol_att / vol_media - 1) * 100 if vol_media else 0
    tp      = prezzo * (1 + TAKE_PROFIT_PCT    / 100)
    atp     = prezzo * (1 + AGGR_TP_PCT        / 100)
    sl      = prezzo * (1 + STOP_LOSS_PCT      / 100)
    hsl     = prezzo * (1 + HARD_STOP_LOSS_PCT / 100)
    return (
        f"🟢 <b>SEGNALE COMPRA — {simbolo}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Prezzo entrata  : {fmt_eur(prezzo)}\n\n"
        f"<b>📊 Indicatori</b>\n"
        f"  RSI(14)          : {rsi}  ✅ &lt; {RSI_SOGLIA}\n"
        f"  MACD             : {macd['macd']}  ✅ crossover rialzista\n"
        f"  Volume attuale   : {fmt_vol(vol_att)}\n"
        f"  Volume medio(6)  : {fmt_vol(vol_media)}\n"
        f"  Variazione vol.  : +{vol_pct:.1f}%  ✅ &gt; +{VOLUME_AUMENTO_PCT}%\n\n"
        f"<b>🎯 Livelli da tenere d'occhio</b>\n"
        f"  TP normale       : {fmt_eur(tp)}  (+{TAKE_PROFIT_PCT}%)\n"
        f"  TP aggressivo    : {fmt_eur(atp)} (+{AGGR_TP_PCT}%)\n"
        f"  Stop Loss        : {fmt_eur(sl)}  ({STOP_LOSS_PCT}%)\n"
        f"  Stop Loss duro   : {fmt_eur(hsl)} ({HARD_STOP_LOSS_PCT}%)\n\n"
        f"⚠️ <i>Segnale algoritmico — non è consulenza finanziaria.</i>\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


def msg_uscita(simbolo: str, prezzo_att: float, prezzo_ent: float,
               tipo: str, pct: float) -> str:
    emoji_map = {
        "TP":      "💰",
        "TP_AGGR": "🚀",
        "SL":      "⚠️",
        "SL_DURO": "🛑",
    }
    testo_map = {
        "TP":      f"TAKE PROFIT +{TAKE_PROFIT_PCT}% raggiunto!",
        "TP_AGGR": f"TAKE PROFIT AGGRESSIVO +{AGGR_TP_PCT}% raggiunto!",
        "SL":      f"STOP LOSS {STOP_LOSS_PCT}% — considera di uscire",
        "SL_DURO": f"STOP LOSS DURO {HARD_STOP_LOSS_PCT}% — CHIUDI LA POSIZIONE",
    }
    return (
        f"{emoji_map[tipo]} <b>{simbolo} — {testo_map[tipo]}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Prezzo attuale  : {fmt_eur(prezzo_att)}\n"
        f"📌 Prezzo entrata  : {fmt_eur(prezzo_ent)}\n"
        f"📈 Variazione      : {'+' if pct >= 0 else ''}{pct:.2f}%\n\n"
        f"⚠️ <i>Segnale algoritmico — non è consulenza finanziaria.</i>\n"
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


def msg_report(analisi: list[dict]) -> str:
    righe = ["📊 <b>REPORT GIORNALIERO</b>\n"]
    for a in analisi:
        stato = "🟢 Rialzista" if (a.get("macd") and a["macd"]["macd"] > a["macd"]["segnale"]) else "🔴 Ribassista"
        righe.append(
            f"<b>{a['simbolo']}</b>  {fmt_eur(a['prezzo'])}\n"
            f"  RSI {a['rsi']}  |  Trend: {stato}"
        )
    righe.append(f"\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    return "\n\n".join(righe)


# ────────────────────────────────────────────────────────────────
# LOGICA PRINCIPALE
# ────────────────────────────────────────────────────────────────

def analizza_crypto(crypto_id: str, simbolo: str) -> dict | None:
    prezzi, volumi = ottieni_dati_orari(crypto_id, giorni=7)
    if len(prezzi) < 50 or len(volumi) < VOLUME_CANDELE + 1:
        print(f"  [{simbolo}] Dati insufficienti ({len(prezzi)} prezzi, {len(volumi)} volumi)")
        return None

    prezzo  = prezzi[-1]
    rsi     = calcola_rsi(prezzi, RSI_PERIODO)
    macd    = calcola_macd(prezzi)
    vol_ok, vol_att, vol_media = controlla_volume(volumi, VOLUME_CANDELE, VOLUME_AUMENTO_PCT)

    if rsi is None or macd is None:
        return None

    return {
        "simbolo":   simbolo,
        "prezzo":    prezzo,
        "rsi":       rsi,
        "macd":      macd,
        "vol_ok":    vol_ok,
        "vol_att":   vol_att,
        "vol_media": vol_media,
    }


def controlla_segnali_ingresso(stato: dict) -> None:
    for crypto_id, simbolo in CRYPTOS.items():
        # Non aprire una nuova posizione se ce n'è già una aperta
        if posizione_aperta(stato, simbolo):
            print(f"  [{simbolo}] Posizione già aperta — skip segnali di ingresso")
            continue

        a = analizza_crypto(crypto_id, simbolo)
        if not a:
            continue

        rsi_ok    = a["rsi"] < RSI_SOGLIA
        macd_ok   = a["macd"]["crossover_rialzista"]
        vol_ok    = a["vol_ok"]

        vol_pct   = (a["vol_att"] / a["vol_media"] - 1) * 100 if a["vol_media"] else 0
        print(
            f"  [{simbolo}] Prezzo {fmt_eur(a['prezzo'])} | "
            f"RSI {a['rsi']} ({'✅' if rsi_ok else '❌'}) | "
            f"MACD crossover {'✅' if macd_ok else '❌'} | "
            f"Vol +{vol_pct:.1f}% {'✅' if vol_ok else '❌'}"
        )

        if rsi_ok and macd_ok and vol_ok:
            print(f"  [{simbolo}] 🟢 TUTTI I CRITERI SODDISFATTI — invio segnale COMPRA")
            invia_messaggio(msg_ingresso(
                simbolo, a["prezzo"], a["rsi"], a["macd"],
                a["vol_att"], a["vol_media"]
            ))
            apri_posizione(stato, simbolo, a["prezzo"])


def controlla_uscite(stato: dict) -> None:
    for crypto_id, simbolo in CRYPTOS.items():
        if not posizione_aperta(stato, simbolo):
            continue

        pos    = stato["posizioni"][simbolo]
        p_ent  = pos["prezzo_entrata"]

        prezzi, _ = ottieni_dati_orari(crypto_id, giorni=1)
        if not prezzi:
            continue
        p_att = prezzi[-1]
        pct   = (p_att / p_ent - 1) * 100

        print(
            f"  [{simbolo}] Posizione aperta | "
            f"Entrata {fmt_eur(p_ent)} | Attuale {fmt_eur(p_att)} | "
            f"Variazione {'+' if pct >= 0 else ''}{pct:.2f}%"
        )

        # ── Take Profit Aggressivo (+15%) ─────────────────────────
        if pct >= AGGR_TP_PCT and not pos["aggr_tp_colpito"]:
            invia_messaggio(msg_uscita(simbolo, p_att, p_ent, "TP_AGGR", pct))
            pos["aggr_tp_colpito"] = True
            pos["tp_colpito"]      = True   # se hai +15% hai già superato +8%
            chiudi_posizione(stato, simbolo)
            print(f"  [{simbolo}] 🚀 TP Aggressivo colpito — posizione chiusa")

        # ── Take Profit (+8%) ─────────────────────────────────────
        elif pct >= TAKE_PROFIT_PCT and not pos["tp_colpito"]:
            invia_messaggio(msg_uscita(simbolo, p_att, p_ent, "TP", pct))
            pos["tp_colpito"] = True
            salva_stato(stato)
            # Non chiudere: lascia correre verso il TP aggressivo
            print(f"  [{simbolo}] 💰 TP colpito — attendo TP aggressivo")

        # ── Stop Loss Duro (-6%) ──────────────────────────────────
        elif pct <= HARD_STOP_LOSS_PCT and not pos.get("sl_duro_colpito"):
            invia_messaggio(msg_uscita(simbolo, p_att, p_ent, "SL_DURO", pct))
            pos["sl_duro_colpito"] = True
            chiudi_posizione(stato, simbolo)
            print(f"  [{simbolo}] 🛑 Stop Loss Duro colpito — posizione chiusa")

        # ── Stop Loss (-4%) ───────────────────────────────────────
        elif pct <= STOP_LOSS_PCT and not pos["sl_colpito"]:
            invia_messaggio(msg_uscita(simbolo, p_att, p_ent, "SL", pct))
            pos["sl_colpito"] = True
            salva_stato(stato)
            print(f"  [{simbolo}] ⚠️ Stop Loss avviso inviato")


# ────────────────────────────────────────────────────────────────
# ENTRY POINT
# ────────────────────────────────────────────────────────────────

def main() -> None:
    print("╔══════════════════════════════════════════╗")
    print("║   🤖 CRYPTO BOT TELEGRAM — Avviato       ║")
    print(f"║   Controllo ogni {CONTROLLA_OGNI_MINUTI} minuti                 ║")
    print(f"║   Crypto monitorate: {', '.join(CRYPTOS.values())}            ║")
    print("╚══════════════════════════════════════════╝\n")

    stato = carica_stato()

    invia_messaggio(
        "🤖 <b>Crypto Bot avviato!</b>\n\n"
        f"📌 Crypto monitorate: <b>{', '.join(CRYPTOS.values())}</b>\n"
        f"⏱ Controllo ogni <b>{CONTROLLA_OGNI_MINUTI} minuti</b>\n\n"
        "<b>Regole di ingresso:</b>\n"
        f"  • RSI(14) &lt; {RSI_SOGLIA}\n"
        f"  • MACD crossover rialzista\n"
        f"  • Volume +{VOLUME_AUMENTO_PCT}% vs media {VOLUME_CANDELE} candele\n\n"
        "<b>Regole di uscita:</b>\n"
        f"  • Take Profit        : +{TAKE_PROFIT_PCT}%\n"
        f"  • TP Aggressivo      : +{AGGR_TP_PCT}%\n"
        f"  • Stop Loss          : {STOP_LOSS_PCT}%\n"
        f"  • Stop Loss Duro     : {HARD_STOP_LOSS_PCT}%\n\n"
        "⚠️ <i>Segnali algoritmici — non è consulenza finanziaria.</i>"
    )

    ultimo_report_ora = -1

    while True:
        adesso = datetime.now()
        print(f"\n[{adesso.strftime('%H:%M:%S')}] ── Controllo mercati ──")

        try:
            controlla_segnali_ingresso(stato)
            controlla_uscite(stato)
        except Exception as e:
            print(f"  [ERRORE] {e}")

        # Report giornaliero
        if adesso.hour == AGGIORNAMENTO_GIORNALIERO_ORA and adesso.hour != ultimo_report_ora:
            try:
                lista = []
                for crypto_id, simbolo in CRYPTOS.items():
                    a = analizza_crypto(crypto_id, simbolo)
                    if a:
                        lista.append(a)
                if lista:
                    invia_messaggio(msg_report(lista))
                ultimo_report_ora = adesso.hour
                print("  → Report giornaliero inviato")
            except Exception as e:
                print(f"  [Report] Errore: {e}")

        time.sleep(CONTROLLA_OGNI_MINUTI * 60)


if __name__ == "__main__":
    main()
