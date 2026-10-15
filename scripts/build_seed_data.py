"""Builds app/data/hospitals.json from the compact seed table below.

Every row is SEED DATA from public knowledge with APPROXIMATE coordinates and departments,
marked verified=false. Verify each row (call the hospital / check its website), then set
verified=true and add source_url. To add every hospital in Nepal from OpenStreetMap, run
scripts/import_osm.py afterwards.

    python -m scripts.build_seed_data
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "hospitals.json"

ALL = ["emergency", "general_medicine", "general_surgery", "cardiology", "neurology", "neurosurgery", "orthopedics",
       "obstetrics_gynecology", "pediatrics", "ophthalmology", "ent", "dermatology", "psychiatry", "oncology",
       "nephrology", "gastroenterology", "pulmonology", "urology", "dental"]
TEACHING = ["emergency", "general_medicine", "general_surgery", "cardiology", "neurology", "orthopedics",
            "obstetrics_gynecology", "pediatrics", "ophthalmology", "ent", "dermatology", "psychiatry",
            "nephrology", "gastroenterology", "pulmonology", "urology", "dental"]
PROVINCIAL = ["emergency", "general_medicine", "general_surgery", "orthopedics", "obstetrics_gynecology", "pediatrics"]
PROVINCIAL_PLUS = PROVINCIAL + ["ophthalmology", "ent", "dermatology", "psychiatry"]
DISTRICT = ["emergency", "general_medicine", "general_surgery", "obstetrics_gynecology", "pediatrics"]

# id, name, name_ne, type, city, district, province, lat, lng, emergency_24h, health_insurance, departments
H = [
    # ---- Kathmandu valley: government and public
    ("tuth", "Tribhuvan University Teaching Hospital", "त्रिभुवन विश्वविद्यालय शिक्षण अस्पताल", "government_teaching", "Maharajgunj", "Kathmandu", "Bagmati", 27.7360, 85.3303, True, True, ALL),
    ("bir", "Bir Hospital (NAMS)", "वीर अस्पताल", "government_teaching", "Mahaboudha", "Kathmandu", "Bagmati", 27.7046, 85.3131, True, True,
     [d for d in ALL if d not in ("obstetrics_gynecology", "pediatrics", "oncology")]),
    ("trauma_center", "National Trauma Center", "राष्ट्रिय ट्रमा सेन्टर", "government_specialty", "Mahaboudha", "Kathmandu", "Bagmati", 27.7050, 85.3127, True, True,
     ["emergency", "orthopedics", "neurosurgery", "general_surgery", "burns"]),
    ("patan", "Patan Hospital (PAHS)", "पाटन अस्पताल", "government_teaching", "Lagankhel", "Lalitpur", "Bagmati", 27.6683, 85.3206, True, True, TEACHING),
    ("civil", "Civil Service Hospital", "निजामती कर्मचारी अस्पताल", "government", "Minbhawan", "Kathmandu", "Bagmati", 27.6866, 85.3389, True, True,
     ["emergency", "general_medicine", "general_surgery", "cardiology", "orthopedics", "obstetrics_gynecology", "pediatrics", "ophthalmology", "ent", "dermatology", "gastroenterology", "urology", "dental"]),
    ("gangalal", "Shahid Gangalal National Heart Centre", "शहीद गंगालाल राष्ट्रिय हृदय केन्द्र", "government_specialty", "Bansbari", "Kathmandu", "Bagmati", 27.7425, 85.3434, True, True, ["emergency", "cardiology"]),
    ("manmohan", "Manmohan Cardiothoracic Vascular and Transplant Center", "मनमोहन कार्डियोथोरासिक भास्कुलर तथा ट्रान्सप्लान्ट केन्द्र", "government_specialty", "Maharajgunj", "Kathmandu", "Bagmati", 27.7358, 85.3310, True, True, ["cardiology", "nephrology"]),
    ("kanti", "Kanti Children's Hospital", "कान्ति बाल अस्पताल", "government_specialty", "Maharajgunj", "Kathmandu", "Bagmati", 27.7340, 85.3300, True, True, ["emergency", "pediatrics"]),
    ("paropakar", "Paropakar Maternity and Women's Hospital", "परोपकार प्रसूति तथा स्त्रीरोग अस्पताल", "government_specialty", "Thapathali", "Kathmandu", "Bagmati", 27.6938, 85.3195, True, True, ["emergency", "obstetrics_gynecology"]),
    ("mental", "Mental Hospital Lagankhel", "मानसिक अस्पताल, लगनखेल", "government_specialty", "Lagankhel", "Lalitpur", "Bagmati", 27.6680, 85.3230, False, True, ["psychiatry"]),
    ("hotc", "Shahid Dharmabhakta National Transplant Centre", "शहीद धर्मभक्त राष्ट्रिय प्रत्यारोपण केन्द्र", "government_specialty", "Dudhpati", "Bhaktapur", "Bagmati", 27.6720, 85.4200, False, True, ["nephrology", "urology"]),
    ("bhaktapur_hosp", "Bhaktapur Hospital", "भक्तपुर अस्पताल", "government", "Bhaktapur", "Bhaktapur", "Bagmati", 27.6720, 85.4280, True, True, PROVINCIAL),
    # ---- Kathmandu valley: non-profit and specialty
    ("tilganga", "Tilganga Institute of Ophthalmology", "तिलगंगा आँखा प्रतिष्ठान", "nonprofit_specialty", "Gaushala", "Kathmandu", "Bagmati", 27.7055, 85.3518, False, None, ["ophthalmology"]),
    ("nepal_eye", "Nepal Eye Hospital", "नेपाल आँखा अस्पताल", "nonprofit_specialty", "Tripureshwor", "Kathmandu", "Bagmati", 27.6950, 85.3110, False, None, ["ophthalmology"]),
    ("ortho_jorpati", "Nepal Orthopaedic Hospital", "नेपाल अर्थोपेडिक अस्पताल", "nonprofit_specialty", "Jorpati", "Kathmandu", "Bagmati", 27.7270, 85.3790, True, None, ["emergency", "orthopedics"]),
    ("bhaktapur_cancer", "Bhaktapur Cancer Hospital", "भक्तपुर क्यान्सर अस्पताल", "nonprofit_specialty", "Dudhpati", "Bhaktapur", "Bagmati", 27.6730, 85.4350, False, None, ["oncology"]),
    ("kirtipur", "Kirtipur Hospital", "कीर्तिपुर अस्पताल", "nonprofit", "Kirtipur", "Kathmandu", "Bagmati", 27.6770, 85.2820, True, None,
     ["emergency", "general_medicine", "general_surgery", "burns", "orthopedics", "obstetrics_gynecology", "pediatrics"]),
    ("kmh", "Kathmandu Model Hospital", "काठमाडौं मोडल अस्पताल", "nonprofit", "Pradarshani Marg", "Kathmandu", "Bagmati", 27.7010, 85.3170, True, None,
     ["emergency", "general_medicine", "general_surgery", "obstetrics_gynecology", "pediatrics", "orthopedics", "ent"]),
    ("dhulikhel", "Dhulikhel Hospital (Kathmandu University Hospital)", "धुलिखेल अस्पताल", "nonprofit_teaching", "Dhulikhel", "Kavrepalanchok", "Bagmati", 27.6178, 85.5552, True, True,
     [d for d in ALL if d not in ("neurosurgery", "urology")]),
    # ---- Kathmandu valley: private
    ("grande", "Grande International Hospital", "ग्रान्डी इन्टरनेसनल अस्पताल", "private", "Dhapasi", "Kathmandu", "Bagmati", 27.7505, 85.3275, True, None, ALL),
    ("norvic", "Norvic International Hospital", "नर्भिक इन्टरनेसनल अस्पताल", "private", "Thapathali", "Kathmandu", "Bagmati", 27.6905, 85.3190, True, None, ALL),
    ("mediciti", "Nepal Mediciti Hospital", "नेपाल मेडिसिटी अस्पताल", "private", "Bhaisepati", "Lalitpur", "Bagmati", 27.6600, 85.3000, True, None, ALL),
    ("hams", "HAMS Hospital", "हाम्स अस्पताल", "private", "Dhumbarahi", "Kathmandu", "Bagmati", 27.7330, 85.3400, True, None, TEACHING),
    ("bnb", "B&B Hospital", "बी एन्ड बी अस्पताल", "private", "Gwarko", "Lalitpur", "Bagmati", 27.6670, 85.3330, True, None,
     ["emergency", "general_medicine", "general_surgery", "orthopedics", "neurosurgery", "urology", "obstetrics_gynecology", "pediatrics", "ent", "gastroenterology"]),
    ("alka", "Alka Hospital", "अल्का अस्पताल", "private", "Jawalakhel", "Lalitpur", "Bagmati", 27.6730, 85.3120, True, None, TEACHING),
    ("kmc", "Kathmandu Medical College Teaching Hospital", "काठमाडौं मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Sinamangal", "Kathmandu", "Bagmati", 27.6960, 85.3530, True, None, TEACHING),
    ("nmc_jorpati", "Nepal Medical College Teaching Hospital", "नेपाल मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Jorpati", "Kathmandu", "Bagmati", 27.7290, 85.3810, True, None, TEACHING),
    ("kist", "KIST Medical College Teaching Hospital", "किस्ट मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Imadol", "Lalitpur", "Bagmati", 27.6650, 85.3420, True, None, TEACHING),
    # ---- Bagmati outside the valley
    ("hetauda", "Hetauda Hospital", "हेटौंडा अस्पताल", "government", "Hetauda", "Makwanpur", "Bagmati", 27.4280, 85.0320, True, True, PROVINCIAL),
    ("bharatpur", "Bharatpur Hospital", "भरतपुर अस्पताल", "government", "Bharatpur", "Chitwan", "Bagmati", 27.6810, 84.4370, True, True, PROVINCIAL_PLUS),
    ("bpkmch", "B.P. Koirala Memorial Cancer Hospital", "बी.पी. कोइराला मेमोरियल क्यान्सर अस्पताल", "government_specialty", "Bharatpur", "Chitwan", "Bagmati", 27.6826, 84.4333, False, True, ["oncology"]),
    ("cmc_chitwan", "Chitwan Medical College Teaching Hospital", "चितवन मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Bharatpur", "Chitwan", "Bagmati", 27.6860, 84.4300, True, None, TEACHING),
    ("cms_chitwan", "College of Medical Sciences Teaching Hospital", "कलेज अफ मेडिकल साइन्सेज शिक्षण अस्पताल", "private_teaching", "Bharatpur", "Chitwan", "Bagmati", 27.6950, 84.4250, True, None, TEACHING),
    # ---- Koshi
    ("bpkihs", "B.P. Koirala Institute of Health Sciences", "बी.पी. कोइराला स्वास्थ्य विज्ञान प्रतिष्ठान", "government_teaching", "Dharan", "Sunsari", "Koshi", 26.8122, 87.2667, True, True, ALL),
    ("koshi", "Koshi Hospital", "कोशी अस्पताल", "government", "Biratnagar", "Morang", "Koshi", 26.4590, 87.2797, True, True, PROVINCIAL + ["ophthalmology", "ent"]),
    ("nobel", "Nobel Medical College Teaching Hospital", "नोबेल मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Biratnagar", "Morang", "Koshi", 26.4700, 87.2900, True, None, TEACHING),
    ("birat_mc", "Birat Medical College Teaching Hospital", "विराट मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Biratnagar", "Morang", "Koshi", 26.4900, 87.2700, True, None, TEACHING),
    ("biratnagar_eye", "Biratnagar Eye Hospital", "विराटनगर आँखा अस्पताल", "nonprofit_specialty", "Rani", "Morang", "Koshi", 26.4300, 87.2800, False, None, ["ophthalmology"]),
    ("mechi", "Mechi Provincial Hospital", "मेची प्रादेशिक अस्पताल", "government", "Bhadrapur", "Jhapa", "Koshi", 26.5440, 88.0950, True, True, DISTRICT),
    ("amda_damak", "AMDA Hospital", "आम्डा अस्पताल", "nonprofit", "Damak", "Jhapa", "Koshi", 26.6600, 87.7000, True, None, PROVINCIAL),
    ("okhaldhunga", "Okhaldhunga Community Hospital", "ओखलढुंगा सामुदायिक अस्पताल", "nonprofit", "Okhaldhunga", "Okhaldhunga", "Koshi", 27.3100, 86.5000, True, None, DISTRICT + ["orthopedics"]),
    # ---- Madhesh
    ("janakpur", "Janakpur Provincial Hospital", "जनकपुर प्रादेशिक अस्पताल", "government", "Janakpur", "Dhanusha", "Madhesh", 26.7290, 85.9260, True, True, PROVINCIAL),
    ("janaki_mc", "Janaki Medical College Teaching Hospital", "जानकी मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Janakpur", "Dhanusha", "Madhesh", 26.7200, 85.9300, True, None, TEACHING),
    ("narayani", "Narayani Hospital", "नारायणी अस्पताल", "government", "Birgunj", "Parsa", "Madhesh", 27.0130, 84.8770, True, True, PROVINCIAL),
    ("national_mc", "National Medical College Teaching Hospital", "नेसनल मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Birgunj", "Parsa", "Madhesh", 27.0200, 84.8700, True, None, TEACHING),
    ("rajbiraj", "Gajendra Narayan Singh Hospital", "गजेन्द्र नारायण सिंह अस्पताल", "government", "Rajbiraj", "Saptari", "Madhesh", 26.5400, 86.7500, True, True, DISTRICT),
    # ---- Gandaki
    ("pahs_pokhara", "Pokhara Academy of Health Sciences (Western Regional Hospital)", "पोखरा स्वास्थ्य विज्ञान प्रतिष्ठान (पश्चिमाञ्चल क्षेत्रीय अस्पताल)", "government_teaching", "Pokhara", "Kaski", "Gandaki", 28.2161, 83.9886, True, True,
     PROVINCIAL_PLUS + ["cardiology", "nephrology"]),
    ("manipal_pokhara", "Manipal Teaching Hospital", "मणिपाल शिक्षण अस्पताल", "private_teaching", "Pokhara", "Kaski", "Gandaki", 28.2050, 83.9640, True, None, ALL),
    ("gandaki_mc", "Gandaki Medical College Teaching Hospital", "गण्डकी मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Pokhara", "Kaski", "Gandaki", 28.2200, 83.9900, True, None, TEACHING),
    ("dhaulagiri", "Dhaulagiri Provincial Hospital", "धौलागिरि प्रादेशिक अस्पताल", "government", "Baglung", "Baglung", "Gandaki", 28.2700, 83.5900, True, True, DISTRICT),
    ("gorkha", "Gorkha Hospital", "गोरखा अस्पताल", "government", "Gorkha", "Gorkha", "Gandaki", 28.0000, 84.6300, True, True, DISTRICT),
    # ---- Lumbini
    ("lumbini", "Lumbini Provincial Hospital", "लुम्बिनी प्रादेशिक अस्पताल", "government", "Butwal", "Rupandehi", "Lumbini", 27.6970, 83.4530, True, True, PROVINCIAL + ["ophthalmology", "ent"]),
    ("ucms", "Universal College of Medical Sciences Teaching Hospital", "युनिभर्सल कलेज अफ मेडिकल साइन्सेज शिक्षण अस्पताल", "private_teaching", "Bhairahawa", "Rupandehi", "Lumbini", 27.5090, 83.4570, True, None, TEACHING),
    ("lumbini_eye", "Lumbini Eye Institute", "लुम्बिनी आँखा प्रतिष्ठान", "nonprofit_specialty", "Bhairahawa", "Rupandehi", "Lumbini", 27.5130, 83.4500, False, None, ["ophthalmology"]),
    ("tansen_mission", "United Mission Hospital Tansen", "युनाइटेड मिसन अस्पताल, तानसेन", "nonprofit", "Tansen", "Palpa", "Lumbini", 27.8680, 83.5450, True, None, PROVINCIAL_PLUS),
    ("lumbini_mc", "Lumbini Medical College Teaching Hospital", "लुम्बिनी मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Prabas", "Palpa", "Lumbini", 27.8800, 83.5600, True, None, TEACHING),
    ("rapti", "Rapti Provincial Hospital", "राप्ती प्रादेशिक अस्पताल", "government", "Tulsipur", "Dang", "Lumbini", 28.1310, 82.2970, True, True, PROVINCIAL),
    ("rapti_ahs", "Rapti Academy of Health Sciences", "राप्ती स्वास्थ्य विज्ञान प्रतिष्ठान", "government_teaching", "Ghorahi", "Dang", "Lumbini", 28.0400, 82.4900, True, True, PROVINCIAL_PLUS),
    ("bheri", "Bheri Hospital", "भेरी अस्पताल", "government", "Nepalgunj", "Banke", "Lumbini", 28.0500, 81.6170, True, True, PROVINCIAL_PLUS),
    ("nepalgunj_mc", "Nepalgunj Medical College Teaching Hospital", "नेपालगञ्ज मेडिकल कलेज शिक्षण अस्पताल", "private_teaching", "Kohalpur", "Banke", "Lumbini", 28.2000, 81.6900, True, None, TEACHING),
    ("prakhar", "Sushil Koirala Prakhar Cancer Hospital", "सुशील कोइराला प्रखर क्यान्सर अस्पताल", "government_specialty", "Khajura", "Banke", "Lumbini", 28.0950, 81.5600, False, True, ["oncology"]),
    # ---- Karnali
    ("surkhet", "Karnali Provincial Hospital", "कर्णाली प्रादेशिक अस्पताल", "government", "Birendranagar", "Surkhet", "Karnali", 28.6010, 81.6340, True, True, PROVINCIAL),
    ("kahs", "Karnali Academy of Health Sciences", "कर्णाली स्वास्थ्य विज्ञान प्रतिष्ठान", "government_teaching", "Jumla", "Jumla", "Karnali", 29.2740, 82.1840, True, True, PROVINCIAL),
    # ---- Sudurpashchim
    ("seti", "Seti Provincial Hospital", "सेती प्रादेशिक अस्पताल", "government", "Dhangadhi", "Kailali", "Sudurpashchim", 28.6950, 80.5900, True, True, PROVINCIAL),
    ("geta_eye", "Geta Eye Hospital", "गेटा आँखा अस्पताल", "nonprofit_specialty", "Geta", "Kailali", "Sudurpashchim", 28.7300, 80.6000, False, None, ["ophthalmology"]),
    ("dadeldhura", "Dadeldhura Hospital", "डडेलधुरा अस्पताल", "government", "Dadeldhura", "Dadeldhura", "Sudurpashchim", 29.3000, 80.5800, True, True, DISTRICT),
    ("doti", "Doti District Hospital", "डोटी जिल्ला अस्पताल", "government", "Dipayal", "Doti", "Sudurpashchim", 29.2600, 80.9400, True, True, DISTRICT),
    ("bayalpata", "Bayalpata Hospital", "बयलपाटा अस्पताल", "government", "Sanfebagar", "Achham", "Sudurpashchim", 29.1500, 81.2300, True, True, DISTRICT),
]


def main() -> None:
    rows = []
    for (hid, name, name_ne, typ, city, district, province, lat, lng, er, ins, depts) in H:
        rows.append({
            "id": hid, "name": name, "name_ne": name_ne, "type": typ, "city": city, "district": district,
            "province": province, "lat": lat, "lng": lng, "emergency_24h": er, "health_insurance": ins,
            "departments": sorted(set(depts)), "phone": None, "website": None,
            "wayfinding": {}, "campus_map_url": None, "billing_notes": None,
            "source": "seed", "source_url": None, "verified": False,
        })
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate id"
    data = {
        "_readme": "SEED DATA. Coordinates, departments and insurance status are approximate and unverified. "
                   "See README 'Hospital data'. health_insurance: true = believed to accept national health insurance, "
                   "null = unknown. wayfinding: {department: 'how to reach it inside the hospital'}.",
        "departments": ALL + ["burns"],
        "hospitals": rows,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} hospitals to {OUT}")


if __name__ == "__main__":
    main()
