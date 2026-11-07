"""Plain words for every KYC outcome, in English and Hindi. Holds no personal data and never reveals a registry value,
so the wording can't be used to learn what a forged document should say."""

DOC_NAME = {"gst": {"en": "GST certificate", "hi": "GST प्रमाणपत्र"}, "udyam": {"en": "Udyam certificate", "hi": "Udyam प्रमाणपत्र"},
            "id": {"en": "Signatory ID", "hi": "हस्ताक्षरकर्ता की ID"}, "bill": {"en": "Address proof", "hi": "पते का प्रमाण"}}

# code: (document, English, Hindi)
ISSUE = {
 "missing_gst": ("gst", "The GST certificate was not provided.", "GST प्रमाणपत्र नहीं दिया गया।"),
 "missing_udyam": ("udyam", "The Udyam certificate was not provided.", "Udyam प्रमाणपत्र नहीं दिया गया।"),
 "no_gst_declaration": ("gst", "No GST certificate was sent, and the box saying the business has no GSTIN wasn't ticked, so a person will check.", "GST प्रमाणपत्र नहीं भेजा गया और \"बिज़नेस के पास GSTIN नहीं है\" वाला बॉक्स नहीं चुना गया, इसलिए कोई व्यक्ति जाँच करेगा।"),
 "missing_id": ("id", "The signatory ID was not provided.", "हस्ताक्षरकर्ता की ID नहीं दी गई।"),
 "missing_bill": ("bill", "The address proof was not provided.", "पते का प्रमाण नहीं दिया गया।"),
 "blurry_gst": ("gst", "The GST certificate is too blurred to read reliably. Please upload a clearer copy.", "GST प्रमाणपत्र इतना धुंधला है कि भरोसे से पढ़ा नहीं जा सकता। कृपया साफ़ कॉपी अपलोड करें।"),
 "blurry_udyam": ("udyam", "The Udyam certificate is too blurred to read reliably. Please upload a clearer copy.", "Udyam प्रमाणपत्र इतना धुंधला है कि भरोसे से पढ़ा नहीं जा सकता। कृपया साफ़ कॉपी अपलोड करें।"),
 "blurry_id": ("id", "The signatory ID is too blurred to read reliably. Please upload a clearer copy.", "हस्ताक्षरकर्ता की ID इतनी धुंधली है कि भरोसे से पढ़ी नहीं जा सकती। कृपया साफ़ कॉपी अपलोड करें।"),
 "blurry_bill": ("bill", "The address proof is too blurred to read reliably. Please upload a clearer copy.", "पते का प्रमाण इतना धुंधला है कि भरोसे से पढ़ा नहीं जा सकता। कृपया साफ़ कॉपी अपलोड करें।"),
 "wrong_gst": ("gst", "This looks like the {other_en}, not the GST certificate. Please check which file you added here.", "यह GST प्रमाणपत्र नहीं, बल्कि {other_hi} लगता है। कृपया देखें कि यहाँ कौन-सी फ़ाइल जोड़ी है।"),
 "wrong_udyam": ("udyam", "This looks like the {other_en}, not the Udyam certificate. Please check which file you added here.", "यह Udyam प्रमाणपत्र नहीं, बल्कि {other_hi} लगता है। कृपया देखें कि यहाँ कौन-सी फ़ाइल जोड़ी है।"),
 "wrong_id": ("id", "This looks like the {other_en}, not the signatory ID. Please check which file you added here.", "यह हस्ताक्षरकर्ता की ID नहीं, बल्कि {other_hi} लगता है। कृपया देखें कि यहाँ कौन-सी फ़ाइल जोड़ी है।"),
 "wrong_bill": ("bill", "This looks like the {other_en}, not the address proof. Please check which file you added here.", "यह पते का प्रमाण नहीं, बल्कि {other_hi} लगता है। कृपया देखें कि यहाँ कौन-सी फ़ाइल जोड़ी है।"),
 "unreadable_gst": ("gst", "We couldn't find the details we need on the GST certificate. Please upload a clear, full, upright copy.", "GST प्रमाणपत्र पर ज़रूरी जानकारी नहीं मिली। कृपया साफ़, पूरी और सीधी कॉपी अपलोड करें।"),
 "unreadable_udyam": ("udyam", "We couldn't find the details we need on the Udyam certificate. Please upload a clear, full, upright copy.", "Udyam प्रमाणपत्र पर ज़रूरी जानकारी नहीं मिली। कृपया साफ़, पूरी और सीधी कॉपी अपलोड करें।"),
 "unreadable_id": ("id", "We couldn't find the details we need on the signatory ID. Please upload a clear, full, upright copy.", "हस्ताक्षरकर्ता की ID पर ज़रूरी जानकारी नहीं मिली। कृपया साफ़, पूरी और सीधी कॉपी अपलोड करें।"),
 "unreadable_bill": ("bill", "We couldn't find the details we need on the address proof. Please upload a clear, full, upright copy.", "पते के प्रमाण पर ज़रूरी जानकारी नहीं मिली। कृपया साफ़, पूरी और सीधी कॉपी अपलोड करें।"),
 "duplicate_gst": ("gst", "We received two different GST certificates, so a person needs to check which one applies.", "हमें दो अलग-अलग GST प्रमाणपत्र मिले, इसलिए कोई व्यक्ति जाँचेगा कि कौन-सा लागू है।"),
 "duplicate_udyam": ("udyam", "We received two different Udyam certificates, so a person needs to check which one applies.", "हमें दो अलग-अलग Udyam प्रमाणपत्र मिले, इसलिए कोई व्यक्ति जाँचेगा कि कौन-सा लागू है।"),
 "duplicate_id": ("id", "We received two different signatory IDs, so a person needs to check which one applies.", "हमें हस्ताक्षरकर्ता की दो अलग-अलग ID मिलीं, इसलिए कोई व्यक्ति जाँचेगा कि कौन-सी लागू है।"),
 "duplicate_bill": ("bill", "We received two different address proofs, so a person needs to check which one applies.", "हमें पते के दो अलग-अलग प्रमाण मिले, इसलिए कोई व्यक्ति जाँचेगा कि कौन-सा लागू है।"),
 "gst_not_found": ("gst", "We could not find this GSTIN in the registry.", "यह GSTIN रजिस्ट्री में नहीं मिला।"),
 "gstin_unread": ("gst", "We couldn't read a GSTIN on the certificate, so we can't confirm it.", "प्रमाणपत्र पर GSTIN पढ़ा नहीं जा सका, इसलिए हम उसकी पुष्टि नहीं कर सकते।"),
 "gstin_unclear": ("gst", "We couldn't read the GSTIN on the certificate clearly enough to confirm it matches the registry.", "प्रमाणपत्र का GSTIN इतना साफ़ नहीं पढ़ा जा सका कि रजिस्ट्री से उसका मिलान पक्का हो।"),
 "gst_number_mismatch": ("gst", "The GSTIN printed on the certificate has a character that differs from the registry record for this business, so it may have been altered.", "प्रमाणपत्र पर छपे GSTIN का एक अक्षर इस बिज़नेस के रजिस्ट्री रिकॉर्ड से अलग है, इसलिए हो सकता है उसमें बदलाव किया गया हो।"),
 "gst_inactive": ("gst", "This GSTIN is {status_en} in the registry, so we can't activate on it.", "यह GSTIN रजिस्ट्री में {status_hi} है, इसलिए हम इस पर सेवा चालू नहीं कर सकते।"),
 "legal_name_mismatch": ("gst", "The legal name on the GST certificate differs from the GST registry.", "GST प्रमाणपत्र पर कानूनी नाम GST रजिस्ट्री से अलग है।"),
 "trade_name_mismatch": ("gst", "The trade name on the GST certificate differs from the GST registry.", "GST प्रमाणपत्र पर व्यापार का नाम GST रजिस्ट्री से अलग है।"),
 "gst_address_mismatch": ("gst", "The address on the GST certificate differs from the GST registry.", "GST प्रमाणपत्र का पता GST रजिस्ट्री से अलग है।"),
 "constitution_mismatch": ("gst", "The business type on the GST certificate differs from the GST registry.", "GST प्रमाणपत्र पर बिज़नेस का प्रकार GST रजिस्ट्री से अलग है।"),
 "liability_date_mismatch": ("gst", "The date of liability on the GST certificate differs from the registration date in the GST registry.", "GST प्रमाणपत्र पर देयता की तारीख GST रजिस्ट्री की पंजीकरण तारीख से अलग है।"),
 "entered_mismatch": ("gst", "The GSTIN you typed differs from the one on the certificate.", "आपका टाइप किया GSTIN प्रमाणपत्र वाले से अलग है।"),
 "gst_format": ("gst", "The registry GSTIN failed the format check.", "रजिस्ट्री का GSTIN फ़ॉर्मेट जाँच में विफल रहा।"),
 "udyam_blank": ("udyam", "The Udyam number is missing from the Udyam certificate.", "Udyam प्रमाणपत्र पर Udyam नंबर नहीं है।"),
 "udyam_format": ("udyam", "The Udyam number on the certificate isn't in the UDYAM-XX-00-0000000 format.", "प्रमाणपत्र का Udyam नंबर UDYAM-XX-00-0000000 फ़ॉर्मेट में नहीं है।"),
 "udyam_not_found": ("udyam", "This Udyam number isn't in the registry.", "यह Udyam नंबर रजिस्ट्री में नहीं है।"),
 "udyam_name_mismatch": ("udyam", "The name on the Udyam certificate differs from the Udyam registry.", "Udyam प्रमाणपत्र का नाम Udyam रजिस्ट्री से अलग है।"),
 "udyam_place_mismatch": ("udyam", "The city or state on the Udyam certificate differs from the Udyam registry.", "Udyam प्रमाणपत्र का शहर या राज्य Udyam रजिस्ट्री से अलग है।"),
 "udyam_vs_gst": ("udyam", "The enterprise name on the Udyam certificate differs from the GST trade name.", "Udyam प्रमाणपत्र पर उद्यम का नाम GST वाले व्यापार के नाम से अलग है।"),
 "bill_date": ("bill", "We couldn't read the date on the address proof.", "पते के प्रमाण की तारीख पढ़ी नहीं जा सकी।"),
 "bill_stale": ("bill", "The address proof is dated {date} ({days} days old). We accept up to {max} days. Please upload a recent bill.", "पते का प्रमाण {date} का है ({days} दिन पुराना)। हम {max} दिन तक का ही स्वीकार करते हैं। कृपया हाल का बिल अपलोड करें।"),
 "bill_future": ("bill", "The address proof is dated {date}, which is in the future.", "पते के प्रमाण की तारीख {date} है, जो भविष्य की है।"),
 "address_mismatch": ("bill", "The address on the bill doesn't match the registered business address.", "बिल का पता बिज़नेस के पंजीकृत पते से मेल नहीं खाता।"),
 "bill_name": ("bill", "The bill is in a different business name.", "बिल किसी दूसरे बिज़नेस के नाम पर है।"),
 "id_date": ("id", "We couldn't read the expiry date on the signatory ID.", "हस्ताक्षरकर्ता की ID की समाप्ति तारीख पढ़ी नहीं जा सकी।"),
 "id_expired": ("id", "The signatory ID expired on {date}. Please upload a valid ID.", "हस्ताक्षरकर्ता की ID {date} को समाप्त हो गई। कृपया मान्य ID अपलोड करें।"),
 "id_number_blank": ("id", "We couldn't read an ID number on the signatory ID.", "हस्ताक्षरकर्ता की ID पर ID नंबर पढ़ा नहीं जा सका।"),
 "id_business": ("id", "The signatory ID is for a different business.", "हस्ताक्षरकर्ता की ID किसी दूसरे बिज़नेस की है।"),
 "signatory_mismatch": ("id", "The name on the signatory ID differs from the proprietor on the GST record.", "हस्ताक्षरकर्ता की ID का नाम GST रिकॉर्ड के मालिक से अलग है।"),
 "signatory_vs_lead": ("id", "The name on the signatory ID differs from the contact person on this business's application.", "हस्ताक्षरकर्ता की ID का नाम इस बिज़नेस के आवेदन में दिए संपर्क व्यक्ति से अलग है।"),
 "signatory_unchecked": ("id", "We have no record to confirm who signs for this business, so a person needs to check the signatory.", "इस बिज़नेस के लिए कौन हस्ताक्षर करता है, इसकी पुष्टि का रिकॉर्ड हमारे पास नहीं है, इसलिए कोई व्यक्ति इसकी जाँच करेगा।"),
}

# check code: (document, English, Hindi)
PASSED = {
 "gst_lookup": ("gst", "Found in the GST registry", "GST रजिस्ट्री में मिला"),
 "no_gstin_declared": ("gst", "You declared the business has no GSTIN, and your plan doesn't need one", "आपने बताया कि बिज़नेस के पास GSTIN नहीं है, और आपके प्लान को इसकी ज़रूरत नहीं"),
 "gstin_match": ("gst", "GSTIN on certificate matches registry", "प्रमाणपत्र का GSTIN रजिस्ट्री से मेल खाता है"),
 "gst_active": ("gst", "GST registration is active", "GST पंजीकरण सक्रिय है"),
 "legal_name": ("gst", "Legal name matches registry", "कानूनी नाम रजिस्ट्री से मेल खाता है"),
 "gst_details": ("gst", "Trade name, address, business type and date match registry", "व्यापार का नाम, पता, बिज़नेस का प्रकार और तारीख रजिस्ट्री से मेल खाते हैं"),
 "udyam_match": ("udyam", "Udyam number and name match registry", "Udyam नंबर और नाम रजिस्ट्री से मेल खाते हैं"),
 "udyam_on_file": ("udyam", "The Udyam registry has a record for this business, so a person can confirm this quickly", "Udyam रजिस्ट्री में इस बिज़नेस का रिकॉर्ड है, इसलिए कोई व्यक्ति इसकी पुष्टि जल्दी कर सकता है"),
 "udyam_place": ("udyam", "City and state match registry", "शहर और राज्य रजिस्ट्री से मेल खाते हैं"),
 "udyam_gst": ("udyam", "Enterprise name matches the GST trade name", "उद्यम का नाम GST वाले व्यापार के नाम से मेल खाता है"),
 "bill_recent": ("bill", "Address proof is recent (within {max} days)", "पते का प्रमाण हाल का है ({max} दिन के भीतर)"),
 "bill_address": ("bill", "Bill address matches registry", "बिल का पता रजिस्ट्री से मेल खाता है"),
 "bill_billed_to": ("bill", "Bill is in this business's name", "बिल इसी बिज़नेस के नाम पर है"),
 "id_valid": ("id", "Signatory ID is valid", "हस्ताक्षरकर्ता की ID मान्य है"),
 "id_for_business": ("id", "Signatory ID is for this business", "हस्ताक्षरकर्ता की ID इसी बिज़नेस की है"),
 "signatory_prop": ("id", "Signatory matches proprietor", "हस्ताक्षरकर्ता मालिक से मेल खाता है"),
 "signatory_lead": ("id", "Signatory matches the contact on the application", "हस्ताक्षरकर्ता आवेदन के संपर्क व्यक्ति से मेल खाता है"),
}

VERIFIED_EN = "All documents are consistent and the business is active in the registry."
VERIFIED_HI = "सभी दस्तावेज़ आपस में मेल खाते हैं और बिज़नेस रजिस्ट्री में सक्रिय है।"
STATUS = {"Cancelled": ("cancelled", "रद्द"), "Suspended": ("suspended", "निलंबित")}


def _fill(text: str, params: dict) -> str:
    return text.format(**params) if params else text


def issue_text(code: str, params: dict, lang: str = "en") -> str:
    _, en, hi = ISSUE[code]
    return _fill(hi if lang == "hi" else en, params)


def issue_doc(code: str) -> str:
    return ISSUE[code][0]


def passed_text(code: str, params: dict, lang: str = "en") -> str:
    _, en, hi = PASSED[code]
    return _fill(hi if lang == "hi" else en, params)


def passed_doc(code: str) -> str:
    return PASSED[code][0]
