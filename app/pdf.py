"""Render a report as a PDF (WeasyPrint shapes Devanagari correctly with the bundled Mukta font)."""

from __future__ import annotations

import base64
import io

import qrcode
import qrcode.image.svg
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config

LABELS = {
    "en": {"brand": "Matrix · hospitalsofnepal.com", "footer": "Matrix — not a medical diagnosis. Emergency: 102",
           "call102": "Call 102 for an ambulance now.", "do_now": "What to do now", "department": "Department",
           "go_to": "Where to go", "km": "km", "er24": "24-hour emergency", "insurance": "Accepts health insurance",
           "unverified": "Details being verified", "directions": "Directions", "open_maps": "Open directions in Google Maps", "scan": "Scan for directions",
           "inside": "Inside the hospital", "billing": "How billing works", "with_insurance": "If you have health insurance",
           "general_billing": "This is the usual process. Confirm the details at the hospital.",
           "other_options": "Other options", "tip": "Tip", "bring": "Bring with you", "ask": "Ask the doctor",
           "warning": "Go to emergency at once if", "schemes": "Programmes that may lower the cost",
           "you_said": "What you told us",
           "vet_now": "Take your animal to a vet now.", "animal": "Animal", "go_to_vet": "Where to take your animal",
           "office": "District government vet office", "find_vets": "Find vets near you on Google Maps",
           "care": "Care at home until the vet visit", "food": "Food and water", "tell_vet": "Tell the vet",
           "vet_warning": "Take it to a vet at once if",
           "vet_footer": "Matrix — not a diagnosis by a vet. Never give human medicines to animals."},
    "ne": {"brand": "Matrix · hospitalsofnepal.com", "footer": "Matrix — यो रोग निदान होइन। आकस्मिक: १०२",
           "call102": "अहिले नै १०२ मा फोन गरेर एम्बुलेन्स बोलाउनुहोस्।", "do_now": "अहिले के गर्ने", "department": "विभाग",
           "go_to": "कहाँ जाने", "km": "किमी", "er24": "२४ घण्टा आकस्मिक सेवा", "insurance": "स्वास्थ्य बीमा लाग्छ",
           "unverified": "विवरण जाँच हुँदै", "directions": "बाटो", "open_maps": "गुगल नक्सामा बाटो हेर्नुहोस्", "scan": "बाटोका लागि स्क्यान गर्नुहोस्",
           "inside": "अस्पतालभित्र कसरी जाने", "billing": "बिल र भुक्तानी कसरी हुन्छ", "with_insurance": "स्वास्थ्य बीमा छ भने",
           "general_billing": "यो सामान्य प्रक्रिया हो। अस्पतालमा पक्का गर्नुहोस्।",
           "other_options": "अरू विकल्प", "tip": "सुझाव", "bring": "साथमा लैजानुहोस्", "ask": "डाक्टरलाई सोध्नुहोस्",
           "warning": "यस्तो भए तुरुन्तै आकस्मिक कक्षमा जानुहोस्", "schemes": "खर्च घटाउन सक्ने कार्यक्रम",
           "you_said": "तपाईंले भन्नुभएको",
           "vet_now": "अहिले नै जनावरलाई पशु चिकित्सककहाँ लैजानुहोस्।", "animal": "जनावर", "go_to_vet": "जनावरलाई कहाँ लैजाने",
           "office": "जिल्लाको सरकारी पशु सेवा कार्यालय", "find_vets": "गुगल नक्सामा नजिकका पशु चिकित्सक खोज्नुहोस्",
           "care": "पशु चिकित्सककहाँ नपुगुन्जेल घरमा हेरचाह", "food": "खाना र पानी", "tell_vet": "पशु चिकित्सकलाई भन्नुहोस्",
           "vet_warning": "यस्तो भए तुरुन्तै पशु चिकित्सककहाँ लैजानुहोस्",
           "vet_footer": "Matrix — यो पशु चिकित्सकको जाँच होइन। जनावरलाई मान्छेको औषधि नदिनुहोस्।"},
}
URGENCY_COLORS = {"emergency": ("#C4281C", "#FBEDEB"), "urgent": ("#B5480F", "#FDF0E7"),
                  "soon": ("#8A6400", "#FFF6DD"), "routine": ("#1F7A4D", "#E9F5EE")}

_env = Environment(loader=FileSystemLoader(config.TEMPLATE_DIR), autoescape=select_autoescape(["html"]))


def _qr_data_uri(url: str) -> str:
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def render_html(report: dict) -> str:
    lang = report.get("lang", "ne")
    color, tint = URGENCY_COLORS.get(report.get("urgency"), URGENCY_COLORS["soon"])
    qr = {h["id"]: _qr_data_uri(h["directions_url"]) for h in report.get("hospitals", [])[:1]}
    return _env.get_template("report.html").render(
        r=report, t=LABELS[lang], qr=qr, color=color, tint=tint, font_dir=config.FONT_DIR.as_uri())


def render_pdf(report: dict) -> bytes:
    from weasyprint import HTML  # imported lazily: heavy, needs system pango

    return HTML(string=render_html(report)).write_pdf()
