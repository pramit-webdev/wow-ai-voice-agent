"""Knowledge base for the Whispers of the Wind (WOW) project.

Facts verified against public listings (official site wowbydivyasree.com,
magicbricks, roofandfloor, upcomingprop, villasinbangalore.co.in) in Aug 2026.
"""

PROJECT = {
    "name": "Whispers of the Wind (WOW)",
    "developer": "Divyasree Developers Private Limited",
    "developer_tagline": "One of India's most trusted developers with 30+ years of delivery",
    "type": "Premium gated villa-plot development",
    "location": "Nandi Valley, near Nandi Hills, Doddaballapura Taluk, Bengaluru Rural",
    "address": (
        "Heggadihalli Village, Doddaballapura Taluk, Bengaluru Rural, Karnataka "
        "(PIN 562110)"
    ),
    "land_area": "38 acres",
    "plots": 207,
    "plot_sizes": "1,200 to 4,000 sq.ft. (1200, 1800, 2003, 2400, 3199, 4000)",
    "base_rate": "₹7,700 per sq.ft. (tentative)",
    "starting_price": "₹92.4 lakh (1,200 sq.ft. plot, inclusive of taxes)",
    "price_range": "₹92.4 lakh – ₹3.08 crore",
    "price_bands": {
        "1200 sq.ft.": "₹92.4 Lakh",
        "1800 sq.ft.": "₹1.39 Cr",
        "2003 sq.ft.": "₹1.54 Cr",
        "2400 sq.ft.": "₹1.85 Cr",
        "3199 sq.ft.": "₹2.46 Cr",
        "4000 sq.ft.": "₹3.08 Cr",
    },
    "possession": "31 December 2029 (phased delivery, project under construction)",
    "rera": "PRM/KA/RERA/1250/301/PR/070525/007718",
    "rera_registered": True,
    "launch": "June 2025",
    "status": "Under construction / ongoing project",
    "usp": [
        "74% open spaces across 38 acres",
        "20,000+ sq.ft. private clubhouse",
        "Eco-parks and landscaped gardens",
        "Panoramic Nandi Hills valley views",
        "Nestled between Dibbagiri Betta and Horagina Betta hills",
        "Gated community with 24x7 security",
        "Wind and sound sculptures, artful landscaping",
        "Wide internal roads and pedestrian-friendly planning",
    ],
    "amenities": [
        "20,000+ sq.ft. private clubhouse with hospitality",
        "Open-air amphitheatre",
        "Pickle-ball court, futsal court, multi-purpose play court",
        "Putt-putt golf, skating rink",
        "Meditational garden, yoga deck, wellness pavilion",
        "Pet park, fitness court, outdoor gym",
        "Bike pods, gazebos, cascade point, boardwalks",
        "Gravity-fed water system (sustainability)",
    ],
    "connectivity": {
        "airport": "~20 minutes from Kempegowda International Airport (KIA)",
        "hebbal": "~50 minutes from Hebbal",
        "devanahalli": "Near Devanahalli, on the NH-7 / airport corridor",
        "future_growth": [
            "Devanahalli Business Park",
            "Aerospace SEZ",
            "Upcoming gondola project (Nandi Hills)",
            "Future IT investment corridor",
        ],
    },
    "target_buyers": ["HNIs", "CXOs", "NRIs", "second-home buyers", "long-term investors"],
    "sales_contact": "+91 7026001236",
    "official_site": "https://wowbydivyasree.com",
    "payments": "Flexible payment plans and EMI support are available for eligible buyers",
}

# Curated answers for common questions (used by the offline fallback engine).
# Each entry is (English, Hindi) - the engine picks the variant to match the
# caller's language. All figures are the verified facts from PROJECT above.
FAQ = {
    "price": (
        "Plots start at 92.4 lakh rupees for a 1,200 square foot plot and go up to "
        "3.08 crore for a 4,000 square foot plot - a tentative base rate of 7,700 "
        "rupees per square foot, inclusive of taxes.",
        "Plots 92.4 lakh rupees se shuru hote hain - 1,200 square foot plot ke liye - "
        "aur 3.08 crore tak, 4,000 square foot plot ke liye. Base rate 7,700 rupees "
        "per square foot hai, taxes inclusive.",
    ),
    "size": (
        "Villa plots range from 1,200 to 4,000 square feet - options include 1,200, "
        "1,800, 2,003, 2,400, 3,199 and 4,000 square feet.",
        "Villa plots 1,200 se 4,000 square feet tak hain - options mein 1,200, 1,800, "
        "2,003, 2,400, 3,199 aur 4,000 square feet shamil hain.",
    ),
    "location": (
        "The project sits in the Nandi Valley near Nandi Hills, about 20 minutes from "
        "Kempegowda International Airport and roughly 50 minutes from Hebbal. "
        "Devanahalli town - with shops, banks, hospitals and schools - is just "
        "minutes away.",
        "Project Nandi Hills ke paas, Nandi Valley mein hai - Kempegowda International "
        "Airport se kareeb 20 minute aur Hebbal se 50 minute. Devanahalli town - shops, "
        "banks, hospitals aur schools ke saath - sirf kuch minute door hai.",
    ),
    "possession": (
        "Possession is expected by 31 December 2029, delivered in phases.",
        "Possession 31 December 2029 tak expected hai, phases mein delivery hogi.",
    ),
    "rera": (
        "Yes, it is fully RERA-registered - registration number "
        "PRM/KA/RERA/1250/301/PR/070525/007718.",
        "Haan, fully RERA-registered hai - registration number "
        "PRM/KA/RERA/1250/301/PR/070525/007718.",
    ),
    "clubhouse": (
        "There's a 20,000+ square foot private clubhouse, plus an amphitheatre, "
        "pickle-ball courts, putt-putt golf, a yoga deck, a meditational garden, "
        "a pet park and more.",
        "20,000+ square foot ka private clubhouse hai, saath mein amphitheatre, "
        "pickle-ball courts, putt-putt golf, yoga deck, meditational garden, "
        "pet park aur bahut kuch.",
    ),
    "openspace": (
        "74% of the 38 acres is open space - eco-parks, landscaped gardens and "
        "pedestrian-friendly paths with panoramic valley views.",
        "38 acres ka 74% open space hai - eco-parks, landscaped gardens aur "
        "pedestrian-friendly paths, valley ke panoramic views ke saath.",
    ),
    "investment": (
        "It's near the Devanahalli Business Park, the Aerospace SEZ and the upcoming "
        "Nandi Hills gondola project - strong drivers for long-term appreciation.",
        "Yeh Devanahalli Business Park, Aerospace SEZ aur upcoming Nandi Hills gondola "
        "project ke paas hai - long-term appreciation ke strong drivers.",
    ),
    "developer": (
        "Whispers of the Wind is by Divyasree Developers, one of India's most trusted "
        "builders with over three decades of delivery across Bengaluru.",
        "Whispers of the Wind Divyasree Developers ka project hai - India ke sabse "
        "bharosemand builders mein se ek, 30+ saalon ka Bengaluru mein delivery record.",
    ),
    "payments": (
        "Yes, flexible payment plans and EMI support are available for eligible "
        "buyers - our property expert will walk you through the instalment schedule "
        "on the follow-up call.",
        "Haan, eligible buyers ke liye flexible payment plans aur EMI support "
        "available hai - hamare property expert instalment schedule follow-up call "
        "par batayenge.",
    ),
    "project": (
        "The project spans 38 acres with 207 premium villa plots, with 74% of the "
        "land kept as open space.",
        "Project 38 acres mein hai, 207 premium villa plots ke saath - aur 74% "
        "land open space ke liye rakha gaya hai.",
    ),
    "infrastructure": (
        "The community is fully gated with 24x7 security, wide internal roads and "
        "a gravity-fed water system for sustainability.",
        "Community fully gated hai - 24x7 security, wide internal roads aur "
        "gravity-fed water system sustainability ke liye.",
    ),
    "booking": (
        "I'd love to set up a follow-up call with one of our property experts who can "
        "walk you through layouts, availability and the booking process.",
        "Main hamare property expert se follow-up call set kar deta hoon jo layouts, "
        "availability aur booking process samjha denge.",
    ),
}
