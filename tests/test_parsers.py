from scripts.parsers import parse_text
BASE='PlayStation 5 Pro Konsole 2 TB '
def test_mediamarkt_sold_out_overrides_cart():
 r=parse_text('MediaMarkt DE',BASE+'Unser Aktionsangebot ist leider ausverkauft In den Warenkorb Lieferung nach Hause 999,00 €')
 assert r.availability=='unavailable' and not r.validated
def test_playstation_direct_sold_out():
 r=parse_text('PlayStation Direct DE',BASE+'Derzeit nicht vorrätig. Schau bald wieder vorbei.')
 assert r.availability=='unavailable'
def test_alternate_not_buyable():
 r=parse_text('Alternate DE',BASE+'€ 899,99 Artikel kann derzeit nicht gekauft werden')
 assert r.price==899.99 and not r.validated
def test_idealo_valid_new_offer():
 r=parse_text('Idealo DE',BASE+'Angebote: Neu ab 1.289,00 €')
 assert r.price==1289 and r.validated
def test_wrong_product_rejected():
 r=parse_text('Amazon.de','DualSense Controller 79,99 € In den Einkaufswagen')
 assert not r.validated and r.price is None
