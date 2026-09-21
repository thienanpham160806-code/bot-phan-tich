# Vendor cuc bo: DNSE OpenAPI Python SDK

`pip install openapi-sdk` (theo huong dan chinh thuc cua DNSE) **khong cai
duoc** — package nay chua duoc publish len PyPI thuc su tinh den luc kiem
tra (19-21/09/2026), du README cua repo goc noi vay. Repo Git cung khong co
`setup.py`/`pyproject.toml` nen `pip install git+https://...` cung khong
chay duoc.

Thu muc nay la ban sao **NGUYEN VAN** cua `python/dnse/` tu repo chinh thuc
<https://github.com/dnse-tech/openapi-sdk> (commit luc tai ve, xem `SOURCE_COMMIT`),
chi them `pyproject.toml` de `pip install -e vendor/dnse-sdk` chay duoc.

## Cach cai

```bash
pip install -e vendor/dnse-sdk
```

## Cap nhat khi DNSE sua SDK

1. Tai lai cac file trong `dnse/` tu repo goc (xem `SOURCE_COMMIT` de biet
   ban dang dung).
2. Chay lai `pip install -e vendor/dnse-sdk` (khong can neu chi sua code,
   editable install da tro thang vao thu muc nay).
3. Neu DNSE cuoi cung publish that len PyPI: xoa thu muc nay, bo dong
   `-e vendor/dnse-sdk` khoi requirements.txt, doi lai `openapi-sdk>=x` binh
   thuong.

## Da xac nhan (khong con la gia dinh)

Doc lai truc tiep tu `spec/dnse-openapi-2026-09-15.yaml` trong repo goc:

- `GET /price/ohlc`: bat buoc `symbol`, `resolution` (`1,3,5,15,30,1h,1D,1W`),
  `from`, `to` (epoch giay). Tra ve `{t,o,h,l,c,v,nextTime}` (mang song song).
- SDK: `client.get_ohlc(bar_type, query={...})` — `bar_type` la loai thi
  truong (`STOCK`/`DERIVATIVE`/`INDEX`), **khong phai** khung thoi gian nen;
  resolution/symbol/from/to nam trong `query`.
- `GET /market/instruments`: tra ve `{"data": [{symbol, marketId, name,
  shortName, listedDate, ...}]}`. `marketId`: `STO`=HOSE, `STX`=HNX,
  `UPX`=UPCOM.
- Moi phuong thuc cua `DNSEClient` tra ve tuple `(status_code, body_text)`,
  `body_text` la CHUOI JSON tho (can `json.loads()`), khong phai dict co san.

Da chinh sua `data/dnse.py` cho khop (xem `_call_ohlc`, `_call_instruments`,
`_normalise_ohlc`, `RESOLUTION_MAP`).
