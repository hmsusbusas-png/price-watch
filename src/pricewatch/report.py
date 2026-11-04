from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .sources import Product
from .storage import Item, Point, Store

HEAD = PatternFill("solid", fgColor="1F2A30")
HEAD_FONT = Font(bold=True, color="FFFFFF")


def _sheet_head(ws, titles: list[str], widths: list[int]) -> None:
    ws.append(titles)
    for i, width in enumerate(widths, 1):
        cell = ws.cell(row=1, column=i)
        cell.fill, cell.font, cell.alignment = HEAD, HEAD_FONT, Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"


def history_workbook(store: Store, path: Path) -> Path:
    """One summary sheet plus a sheet with history and a line chart per item."""
    wb = Workbook()
    summary = wb.active
    summary.title = "Сводка"
    _sheet_head(summary, ["№", "Товар", "Источник", "Сейчас, ₽", "Мин., ₽", "Макс., ₽", "Замеров", "Ссылка"],
                [5, 46, 10, 12, 12, 12, 10, 50])
    for item in store.items():
        points = store.history(item.id)
        prices = [p.price for p in points]
        summary.append([item.id, item.name, item.kind, prices[-1] if prices else None,
                        min(prices) if prices else None, max(prices) if prices else None, len(prices), _link(item)])
        if points:
            _item_sheet(wb, item, points)
    for row in summary.iter_rows(min_row=2, min_col=4, max_col=6):
        for cell in row:
            cell.number_format = "#,##0.00"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _item_sheet(wb: Workbook, item: Item, points: list[Point]) -> None:
    ws = wb.create_sheet(f"{item.id} {item.name}"[:31].replace("/", "-").replace(":", " "))
    _sheet_head(ws, ["Когда", "Цена, ₽"], [20, 12])
    for p in points:
        ws.append([p.at, p.price])
        ws.cell(row=ws.max_row, column=1).number_format = "dd.mm.yyyy hh:mm"
        ws.cell(row=ws.max_row, column=2).number_format = "#,##0.00"
    if len(points) > 1:
        chart = LineChart()
        chart.title = item.name[:60]
        chart.y_axis.title = "₽"
        chart.height, chart.width = 8, 18
        chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=ws.max_row), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=ws.max_row))
        chart.legend = None
        ws.add_chart(chart, "D2")


def search_workbook(products: list[Product], path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Поиск"
    titles = ["Артикул", "Название", "Бренд", "Цена, ₽", "До скидки, ₽", "Скидка, %", "Рейтинг", "Отзывов", "Ссылка"]
    _sheet_head(ws, titles, [12, 50, 18, 12, 14, 10, 9, 10, 48])
    for p in products:
        ws.append([p.sku, p.title, p.brand, p.price, p.old_price, p.discount, p.rating, p.reviews, p.url])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def chart_png(item: Item, points: list[Point], path: Path) -> Path:
    if len(points) < 2:
        raise ValueError("для графика нужно хотя бы два замера с разной ценой")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    xs = [p.at for p in points]
    ys = [p.price for p in points]
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    ax.step(xs, ys, where="post", color="#1f2a30", linewidth=2)
    ax.scatter(xs, ys, color="#c4301a", s=18, zorder=3)
    low = ys.index(min(ys))
    ax.annotate(f"мин. {min(ys):,.0f} ₽".replace(",", " "), (xs[low], ys[low]),
                xytext=(0, 10), textcoords="offset points", ha="right" if low == len(xs) - 1 else "center",
                fontsize=9, color="#c4301a")
    ax.margins(x=0.03, y=0.15)
    ax.set_title(item.name[:70], fontsize=12, loc="left")
    ax.set_ylabel("₽")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def _link(item: Item) -> str:
    return item.target if item.kind == "url" else f"https://www.wildberries.ru/catalog/{item.target}/detail.aspx"
