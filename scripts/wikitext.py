"""Wikitext -> readable blocks. Copied from mariadb-system-versioning-wikipedia/history.py
(MIT, MariaDB Foundation 2026). Not MediaWiki's parser: templates, tables, references and
galleries are dropped, links become plain words, headings and lists are kept.

Changes from the starter: headings carry their level ('h2', 'h3', ...), galleries, magic words
and bare external links are dropped, HTML entities (&nbsp;) decoded, and empty blocks skipped.
"""
import html
import re


def _drop_nested(text, start, end):
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith(start, i):
            depth += 1; i += len(start)
        elif depth and text.startswith(end, i):
            depth -= 1; i += len(end)
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def clean(wikitext):
    """Wikitext -> a list of (kind, text) blocks: kind is 'h2'/'h3'/... (heading), 'li' or 'p'."""
    t = re.sub(r"<!--.*?-->", "", wikitext, flags=re.S)
    t = re.sub(r"<ref[^>]*/>", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<(gallery|math|syntaxhighlight|timeline)[^>]*>.*?</\1>", "", t, flags=re.S | re.I)
    t = _drop_nested(t, "{{", "}}")
    t = _drop_nested(t, "{|", "|}")
    t = re.sub(r"\[\[(?:Tiedosto|Kuva|File|Image|Luokka|Category):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", t)
    t = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\]", "", t)
    t = re.sub(r"__[A-Z]+__", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t.replace("'''", "").replace("''", "")).replace("\xa0", " ").replace("\xad", "")
    t = re.sub(r"\(\s*\)", "", re.sub(r"[,;]\s*\)", ")", t))      # "(SFB, )" left by a template
    blocks = []
    for line in t.split("\n"):
        line = line.strip()
        if not line:
            continue
        heading = re.match(r"^(=+)\s*(.*?)\s*=+$", line)
        if heading:
            blocks.append((f"h{len(heading.group(1))}", heading.group(2)))
        elif line[0] in "*#":
            if line.lstrip("*#: "):
                blocks.append(("li", line.lstrip("*#: ")))
        elif line[0] not in "|!:;":
            blocks.append(("p", line))
    return blocks


if __name__ == "__main__":
    sample = """'''Talvisota'''<ref name="a">x</ref> käytiin [[Suomi|Suomen]] ja [[Neuvostoliitto|NL:n]] välillä.{{lähde}}
Kuolleita 26&nbsp;662.<ref name="b" /> Lakiehdo&shy;tus (SFB, {{lang|sv|x}}) ja ({{lang|sv|y}}).
{{Infobox sota
| nimi = {{lang|fi|Talvisota}}
}}
[[Tiedosto:Kuva.jpg|pieni|Kuvateksti [[Linkki]]]]
<gallery>
Tiedosto:A.jpg|Kuva A
</gallery>
== Tausta ==
=== Neuvottelut ===
* {{Cite web|url=x}}
* [https://yle.fi Yle] ja [https://example.org]
{| class="wikitable"
| solu
|}
[[Luokka:Talvisota]]"""
    got = clean(sample)
    assert got == [("p", "Talvisota käytiin Suomen ja NL:n välillä."), ("p", "Kuolleita 26 662. Lakiehdotus (SFB) ja ."),
                   ("h2", "Tausta"),
                   ("h3", "Neuvottelut"), ("li", "Yle ja")], got
    print("ok")
