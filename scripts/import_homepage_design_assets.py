"""Extract public artwork from the supplied self-contained HTML design.

Only decorative assets are imported. Product/category/brand records remain
managed by Odoo; no prototype records, routing or account scripts are imported.
"""
import argparse
import base64
import re
from io import BytesIO
from pathlib import Path

from lxml import html
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--reference-output', type=Path)
    args = parser.parse_args()
    document = html.fromstring(args.source.read_bytes())
    root = Path(__file__).resolve().parents[1] / 'custom_addons/b2b_website/static/src'
    target = root / 'img/homepage'
    target.mkdir(parents=True, exist_ok=True)

    def decode(uri):
        return Image.open(BytesIO(base64.b64decode(uri.split(',', 1)[1])))

    reference_node = document.xpath('//*[@id="reference-artwork"]')[0]
    reference = decode(reference_node.get('href'))
    scale = reference.width / float(reference_node.get('width'))
    if args.reference_output:
        reference.save(args.reference_output)

    def write_photo(image, name, width=1200):
        image = image.convert('RGB')
        if image.width > width:
            image.thumbnail((width, width))
        image.save(target / (name + '.webp'), 'WEBP', quality=88, method=6)

    def crop(viewbox, name, remove_caption=False):
        x, y, width, height = map(float, viewbox.split())
        # The reference screenshot has a caption in its bottom scene strip;
        # the production caption remains live HTML, not baked into the photo.
        if remove_caption:
            height *= .78
        box = tuple(round(value * scale) for value in (x, y, x + width, y + height))
        write_photo(reference.crop(box), name)

    crop(document.xpath('//*[contains(@class,"hero-photo")]//svg/@viewbox')[0], 'hero')
    for scene in document.xpath('//*[@data-solution]'):
        name = scene.get('data-solution').lower().replace(' ', '-')
        svg = scene.xpath('.//svg[@viewbox]')
        if svg:
            crop(svg[0].get('viewbox'), name, remove_caption=True)
        else:
            write_photo(decode(scene.xpath('.//img/@src')[0]), name, width=1000)

    logo = decode(document.xpath('//img[contains(@class,"hub-logo")]/@src')[0])
    logo.save(target / 'wordmark.png', optimize=True)
    font_target = root / 'fonts/homepage'
    font_target.mkdir(parents=True, exist_ok=True)
    styles = '\n'.join(document.xpath('//style/text()'))
    for family, filename in (('Hub Inter', 'inter.woff2'), ('Hub DM Sans', 'dm-sans.woff2')):
        face = next(face for face in re.findall(r'@font-face\s*\{([^{}]+)\}', styles)
                    if "font-family:'%s'" % family in face)
        encoded = re.search(r'base64,([^\)\s]+)', face).group(1).rstrip("'\"")
        (font_target / filename).write_bytes(base64.b64decode(encoded))

    # Keep the original vector icons, but give every symbol a unique prefix.
    # External <use> references avoid duplicating the sprite on every page.
    from lxml import etree
    sprite = etree.Element('{http://www.w3.org/2000/svg}svg', nsmap={None: 'http://www.w3.org/2000/svg'})
    for symbol in document.xpath('//symbol[starts-with(@id,"icon-")]'):
        clean = etree.fromstring(etree.tostring(symbol, with_tail=False))
        clean.set('id', 'ph-' + clean.get('id'))
        if clean.get('viewbox'):
            clean.set('viewBox', clean.attrib.pop('viewbox'))
        sprite.append(clean)
    (target / 'icons.svg').write_bytes(etree.tostring(sprite, encoding='utf-8', xml_declaration=True))
    waves = document.xpath('//svg[contains(@class,"service-waves")]')[0]
    waves = etree.fromstring(etree.tostring(waves, with_tail=False))
    waves.set('xmlns', 'http://www.w3.org/2000/svg')
    waves.attrib.pop('class', None)
    waves.attrib.pop('aria-hidden', None)
    for node in waves.iter():
        if node.tag == 'lineargradient':
            node.tag = 'linearGradient'
        for lower, camel in (('viewbox', 'viewBox'), ('preserveaspectratio', 'preserveAspectRatio')):
            if node.get(lower):
                node.set(camel, node.attrib.pop(lower))
    (target / 'services-waves.svg').write_bytes(etree.tostring(waves, encoding='utf-8', xml_declaration=True))
    print('Imported decorative assets:', ', '.join(p.name for p in sorted(target.iterdir())))
    print('Total bytes:', sum(p.stat().st_size for p in target.iterdir()))


if __name__ == '__main__':
    main()
