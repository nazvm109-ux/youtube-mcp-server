import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("moy-server")

# Здесь хранится список любимых каналов (файл появится сам)
FAYL_KANALOV = Path(__file__).parent / "kanaly.json"

# Притворяемся браузером, а cookie SOCS убирает окно согласия YouTube в Европе
ZAGOLOVKI = {"User-Agent": "Mozilla/5.0", "Cookie": "SOCS=CAI"}

ATOM = "{http://www.w3.org/2005/Atom}"


def skachat(url):
    zapros = urllib.request.Request(url, headers=ZAGOLOVKI)
    with urllib.request.urlopen(zapros, timeout=15) as otvet:
        return otvet.read().decode("utf-8")


def zagruzit_kanaly():
    if FAYL_KANALOV.exists():
        return json.loads(FAYL_KANALOV.read_text(encoding="utf-8"))
    return {}


def sohranit_kanaly(kanaly):
    FAYL_KANALOV.write_text(
        json.dumps(kanaly, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def nayti_id_kanala(kanal):
    """Из ссылки или @имени достаёт ID канала (начинается с UC)"""
    nayden = re.search(r"(UC[\w-]{22})", kanal)
    if nayden:
        return nayden.group(1)

    imya = kanal.strip().rstrip("/").split("/")[-1]
    if not imya.startswith("@"):
        imya = "@" + imya
    stranica = skachat(f"https://www.youtube.com/{imya}")
    nayden = re.search(r'feeds/videos\.xml\?channel_id=(UC[\w-]{22})', stranica)
    if not nayden:
        nayden = re.search(r'"externalId":"(UC[\w-]{22})"', stranica)
    if not nayden:
        raise ValueError(f"Не нашёл канал {imya}")
    return nayden.group(1)


def poluchit_video(id_kanala):
    """Скачивает RSS-ленту канала: название канала и список последних видео"""
    xml = ET.fromstring(skachat(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={id_kanala}"
    ))
    nazvanie = xml.findtext(f"{ATOM}title")
    video = []
    for zapis in xml.findall(f"{ATOM}entry"):
        video.append({
            "nazvanie": zapis.findtext(f"{ATOM}title"),
            "ssylka": zapis.find(f"{ATOM}link").get("href"),
            "data": datetime.fromisoformat(zapis.findtext(f"{ATOM}published")),
        })
    return nazvanie, video


@mcp.tool()
def privet(imya: str) -> str:
    """Здоровается с человеком по имени"""
    return f"Привет, {imya}! Это мой первый MCP-сервер!"


@mcp.tool()
def dobavit_kanal(kanal: str) -> str:
    """Добавляет YouTube-канал в список любимых. Принимает ссылку на канал или @имя, например @MrBeast"""
    id_kanala = nayti_id_kanala(kanal)
    nazvanie, _ = poluchit_video(id_kanala)
    kanaly = zagruzit_kanaly()
    kanaly[nazvanie] = id_kanala
    sohranit_kanaly(kanaly)
    return f"Канал «{nazvanie}» добавлен в любимые"


@mcp.tool()
def moi_kanaly() -> str:
    """Показывает список любимых YouTube-каналов"""
    kanaly = zagruzit_kanaly()
    if not kanaly:
        return "Список пуст. Добавьте канал через dobavit_kanal."
    return "\n".join(f"- {nazvanie}" for nazvanie in kanaly)


@mcp.tool()
def udalit_kanal(nazvanie: str) -> str:
    """Удаляет YouTube-канал из списка любимых по его названию"""
    kanaly = zagruzit_kanaly()
    if nazvanie not in kanaly:
        return f"Канала «{nazvanie}» нет в списке. Есть: {', '.join(kanaly)}"
    del kanaly[nazvanie]
    sohranit_kanaly(kanaly)
    return f"Канал «{nazvanie}» удалён"


@mcp.tool()
def novye_video(dney: int = 3) -> str:
    """Проверяет, вышли ли новые видео у любимых YouTube-каналов за последние N дней (по умолчанию 3)"""
    kanaly = zagruzit_kanaly()
    if not kanaly:
        return "Список пуст. Добавьте канал через dobavit_kanal."

    granica = datetime.now(timezone.utc) - timedelta(days=dney)
    stroki = []
    for nazvanie, id_kanala in kanaly.items():
        try:
            _, video = poluchit_video(id_kanala)
        except Exception as oshibka:
            stroki.append(f"{nazvanie}: не удалось проверить ({oshibka})")
            continue
        svezhie = [v for v in video if v["data"] >= granica]
        if not svezhie:
            stroki.append(f"{nazvanie}: новых видео нет")
            continue
        stroki.append(f"{nazvanie}: новых видео — {len(svezhie)}")
        for v in svezhie:
            stroki.append(f"  • {v['nazvanie']} ({v['data'].astimezone():%d.%m %H:%M}) {v['ssylka']}")
    return "\n".join(stroki)

@mcp.tool()
def kurs_valyuty(kod: str) -> str:
    """Показывает курс валюты к польскому злотому и обратно (сколько валюты за 1 злотый) по данным NBP. kod — код валюты, например USD, EUR, UAH"""
    url = f"https://api.nbp.pl/api/exchangerates/rates/a/{kod.lower()}/?format=json"
    dannye = json.loads(skachat(url))
    kurs = dannye["rates"][0]["mid"]
    data = dannye["rates"][0]["effectiveDate"]
    obratno = round(1 / kurs, 2)
    return (
        f"1 {kod.upper()} = {kurs} злотых\n"
        f"1 злотый = {obratno} {kod.upper()}\n"
        f"(курс на {data})"
    )



if __name__ == "__main__":
    mcp.run(transport="stdio")