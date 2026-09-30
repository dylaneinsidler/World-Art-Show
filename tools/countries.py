"""Turns museum nationality words ("Ghanaian", "Chinese American") and Wikidata country names into
the country names shown on screen."""

import re

COUNTRIES = """
Afghanistan: Afghan, Afghani | Albania: Albanian | Algeria: Algerian | Andorra: Andorran | Angola: Angolan
Antigua and Barbuda: Antiguan | Argentina: Argentine, Argentinian, Argentinean | Armenia: Armenian
Australia: Australian, Aboriginal Australian, Aboriginal, Torres Strait Islander | Austria: Austrian
Azerbaijan: Azerbaijani, Azeri | Bahamas: Bahamian | Bahrain: Bahraini | Bangladesh: Bangladeshi
Barbados: Barbadian, Bajan | Belarus: Belarusian, Belarussian, Byelorussian | Belgium: Belgian, Flemish
Belize: Belizean | Benin: Beninese, Beninois | Bermuda: Bermudian | Bhutan: Bhutanese | Bolivia: Bolivian
Bosnia and Herzegovina: Bosnian, Herzegovinian | Botswana: Botswanan, Motswana, Batswana | Brazil: Brazilian
Brunei: Bruneian | Bulgaria: Bulgarian | Burkina Faso: Burkinabe, Burkinabè, Burkinabé | Burundi: Burundian
Cambodia: Cambodian, Khmer | Cameroon: Cameroonian | Canada: Canadian, First Nations, Inuit, Métis, Metis
Cape Verde: Cape Verdean | Central African Republic: Central African | Chad: Chadian | Chile: Chilean
China: Chinese, Tibetan | Colombia: Colombian | Comoros: Comoran, Comorian | Congo: Congolese
Democratic Republic of the Congo: Congolese (DRC), Zairean, Zairian | Costa Rica: Costa Rican
Côte d'Ivoire: Ivorian, Ivoirian, Ivory Coast | Croatia: Croatian, Croat | Cuba: Cuban | Cyprus: Cypriot
Czechia: Czech, Bohemian, Moravian | Denmark: Danish, Dane | Djibouti: Djiboutian
Dominican Republic: Dominican | Ecuador: Ecuadorian, Ecuadorean | Egypt: Egyptian | El Salvador: Salvadoran, Salvadorian
England: English | Eritrea: Eritrean | Estonia: Estonian | Eswatini: Swazi | Ethiopia: Ethiopian
Faroe Islands: Faroese | Fiji: Fijian | Finland: Finnish, Finn | France: French, Breton | Gabon: Gabonese
Gambia: Gambian | Georgia: Georgian | Germany: German | Ghana: Ghanaian, Ghanian | Greece: Greek
Greenland: Greenlandic, Greenlander | Grenada: Grenadian | Guatemala: Guatemalan | Guinea: Guinean
Guinea-Bissau: Bissau-Guinean | Guyana: Guyanese | Haiti: Haitian | Honduras: Honduran
Hong Kong: Hong Kong, Hongkonger, Hong Konger | Hungary: Hungarian, Magyar | Iceland: Icelandic, Icelander
India: Indian | Indonesia: Indonesian, Balinese, Javanese | Iran: Iranian, Persian | Iraq: Iraqi
Ireland: Irish | Israel: Israeli | Italy: Italian, Sicilian | Jamaica: Jamaican | Japan: Japanese
Jordan: Jordanian | Kazakhstan: Kazakh, Kazakhstani | Kenya: Kenyan | Kosovo: Kosovar, Kosovan
Kuwait: Kuwaiti | Kyrgyzstan: Kyrgyz, Kirghiz | Laos: Lao, Laotian | Latvia: Latvian, Lettish
Lebanon: Lebanese | Lesotho: Basotho, Mosotho | Liberia: Liberian | Libya: Libyan
Liechtenstein: Liechtensteiner | Lithuania: Lithuanian | Luxembourg: Luxembourgish, Luxembourger
Macau: Macanese | Madagascar: Malagasy | Malawi: Malawian | Malaysia: Malaysian | Maldives: Maldivian
Mali: Malian | Malta: Maltese | Martinique: Martinican | Mauritania: Mauritanian | Mauritius: Mauritian
Mexico: Mexican | Moldova: Moldovan | Monaco: Monégasque, Monegasque | Mongolia: Mongolian, Mongol
Montenegro: Montenegrin | Morocco: Moroccan | Mozambique: Mozambican | Myanmar: Burmese, Myanmar
Namibia: Namibian | Nepal: Nepalese, Nepali | Netherlands: Dutch, Netherlandish, Netherlander
New Zealand: New Zealander, New Zealand, Kiwi, Māori, Maori | Nicaragua: Nicaraguan | Niger: Nigerien
Nigeria: Nigerian, Yoruba, Igbo, Hausa | North Korea: North Korean | North Macedonia: Macedonian
Northern Ireland: Northern Irish | Norway: Norwegian, Sámi, Sami | Oman: Omani | Pakistan: Pakistani
Palestine: Palestinian | Panama: Panamanian | Papua New Guinea: Papua New Guinean | Paraguay: Paraguayan
Peru: Peruvian | Philippines: Filipino, Filipina, Philippine | Poland: Polish, Pole | Portugal: Portuguese
Puerto Rico: Puerto Rican, Nuyorican | Qatar: Qatari | Romania: Romanian, Rumanian | Russia: Russian
Rwanda: Rwandan, Rwandese | Saint Lucia: Saint Lucian, St. Lucian | Samoa: Samoan
Saudi Arabia: Saudi, Saudi Arabian | Scotland: Scottish, Scot, Scots | Senegal: Senegalese
Serbia: Serbian, Serb | Sierra Leone: Sierra Leonean | Singapore: Singaporean | Slovakia: Slovak, Slovakian
Slovenia: Slovenian, Slovene | Somalia: Somali | South Africa: South African | South Korea: South Korean, Korean
South Sudan: South Sudanese | Spain: Spanish, Catalan, Basque, Galician | Sri Lanka: Sri Lankan, Sinhalese
Sudan: Sudanese | Suriname: Surinamese | Sweden: Swedish, Swede | Switzerland: Swiss | Syria: Syrian
Taiwan: Taiwanese | Tajikistan: Tajik, Tajikistani | Tanzania: Tanzanian | Thailand: Thai
Togo: Togolese | Tonga: Tongan | Trinidad and Tobago: Trinidadian, Tobagonian, Trinidadian and Tobagonian
Tunisia: Tunisian | Turkey: Turkish, Türkiye | Turkmenistan: Turkmen | Uganda: Ugandan | Ukraine: Ukrainian
United Arab Emirates: Emirati | United Kingdom: British, Briton, UK | United States: American, US, U.S.,
Native American, African American, African-American, Chicano, Chicana, Chicanx, Hawaiian, Native Hawaiian, Alaska Native
Uruguay: Uruguayan | Uzbekistan: Uzbek, Uzbekistani | Venezuela: Venezuelan | Vietnam: Vietnamese
Wales: Welsh | Yemen: Yemeni | Zambia: Zambian | Zimbabwe: Zimbabwean
"""

NATIONALITY = {}
for entry in re.split(r'\s*\|\s*|\n(?=[A-Z][^:\n]*:)', COUNTRIES.strip()):
    country, _, words = entry.partition(':')
    for word in re.split(r',\s*', words.replace('\n', ' ')):
        if word.strip():
            NATIONALITY[word.strip().casefold()] = country.strip()
    NATIONALITY[country.strip().casefold()] = country.strip()
NAMES = set(NATIONALITY.values())

# Misspellings seen in the collections.
NATIONALITY.update({'ukranian': 'Ukraine', 'japanse': 'Japan', 'venuzuelan': 'Venezuela', 'america': 'United States',
                    'faroeish': 'Faroe Islands', 'botswanian': 'Botswana', 'shipibo': 'Peru'})

# US museums often record Native artists by nation ("Diné", "Santa Clara Pueblo and American").
NATIVE_US = re.compile(r"\b(?:[\w-]+ ){0,2}(?:Pueblo|Nation)\b|\b(?:Diné|Dine|Navajo|Hopi(?:-Tewa)?|Tewa|Acoma|Zuni|Zuñi|"
                       r"(?:Cheyenne River |Oglala |Sicangu |Hunkpapa )?Lakota|Dakota|Chickasaw|Cherokee|Choctaw|Seneca|"
                       r"(?:Match-e-be-nash-she-wish )?Pott?awatomi|Ojibwe|Anishinaabe|Ho-Chunk|Kiowa|Comanche|"
                       r"Apache|Muscogee|Seminole|Osage|Blackfeet|(?:Northern )?Cheyenne|(?:Northern )?Arapaho|Shoshone|Paiute|Tlingit|"
                       r"Passamaquoddy|Penobscot|Piikani|Jemez|(?:Lac Courte Oreilles )?Ojibwe|"
                       r"Yup'ik|Iñupiaq|Inupiaq)\b")

# Wikidata country names that differ from the ones above, and former countries (skipped: an artist born
# in the Soviet Union usually also lists the country they're a citizen of today).
WIKIDATA_NAMES = {
    "People's Republic of China": 'China', 'United States of America': 'United States',
    'Kingdom of the Netherlands': 'Netherlands', 'Kingdom of Denmark': 'Denmark', 'Republic of Ireland': 'Ireland',
    'Republic of China': 'Taiwan', 'State of Palestine': 'Palestine', 'Czech Republic': 'Czechia',
    'Republic of the Congo': 'Congo', 'Ivory Coast': "Côte d'Ivoire", 'The Gambia': 'Gambia',
    'Kingdom of Norway': 'Norway', 'Kingdom of Sweden': 'Sweden', 'Kingdom of Spain': 'Spain',
    'Kingdom of Belgium': 'Belgium', 'Federal Republic of Germany': 'Germany', 'Republic of Korea': 'South Korea',
    "Democratic People's Republic of Korea": 'North Korea', 'Russian Federation': 'Russia', 'Türkiye': 'Turkey',
    'Georgia': 'Georgia', 'Kingdom of Greece': 'Greece', 'Hong Kong SAR': 'Hong Kong', 'Macao': 'Macau',
    'Kingdom of Italy': '', 'German Reich': '', 'Soviet Union': '', 'Yugoslavia': '', 'Socialist Federal Republic of Yugoslavia': '',
    'Federal Republic of Yugoslavia': '', 'Serbia and Montenegro': '', 'Czechoslovakia': '', 'East Germany': '',
    "German Democratic Republic": '', 'West Germany': 'Germany', 'Russian Empire': '', 'Austria-Hungary': '',
    'Ottoman Empire': '', 'British Raj': '', 'Mandatory Palestine': '', 'Weimar Republic': '', 'Nazi Germany': '',
    'Second Polish Republic': '', "Polish People's Republic": 'Poland', 'Kingdom of Hungary': '',
    'Kingdom of Romania': '', 'Kingdom of Bulgaria': '', 'Kingdom of Yugoslavia': '', 'Empire of Japan': '',
    'Dominion of Canada': 'Canada', 'Union of South Africa': 'South Africa', 'French Algeria': '',
    'Belgian Congo': '', 'Portuguese Mozambique': '', 'Southern Rhodesia': '', 'Rhodesia': '', 'Zaire': '',
    'Ukrainian Soviet Socialist Republic': '', 'Russian Soviet Federative Socialist Republic': '',
    'Byelorussian Soviet Socialist Republic': '', 'Georgian Soviet Socialist Republic': '',
    'Armenian Soviet Socialist Republic': '', 'Estonian Soviet Socialist Republic': '',
    'Latvian Soviet Socialist Republic': '', 'Lithuanian Soviet Socialist Republic': '',
    'Kingdom of Egypt': '', 'Kingdom of Iraq': '', 'Pahlavi Iran': '', 'Imperial State of Iran': '',
    'Republic of Vietnam': '', 'South Vietnam': '', 'North Vietnam': 'Vietnam', 'Tanganyika': '',
    'Kingdom of Afghanistan': '', 'Kingdom of Laos': '', 'Khmer Republic': '', 'Burma': 'Myanmar',
    'Swaziland': 'Eswatini', 'Republic of Macedonia': 'North Macedonia', 'Cape Verde': 'Cape Verde',
    'Czech Socialist Republic': '', 'Slovak Socialist Republic': '', 'Free State of Prussia': '',
    'Commonwealth of Puerto Rico': 'Puerto Rico', 'British Hong Kong': 'Hong Kong', 'Taiwan': 'Taiwan', 'Palestine': 'Palestine',
    # Country names as DeviantArt profiles spell them (the ISO list).
    'Korea, Republic of': 'South Korea', "Korea, Democratic People's Republic of": 'North Korea',
    'Viet Nam': 'Vietnam', 'Iran, Islamic Republic of': 'Iran', 'Taiwan, Province of China': 'Taiwan',
    'Syrian Arab Republic': 'Syria', 'Venezuela, Bolivarian Republic of': 'Venezuela',
    'Bolivia, Plurinational State of': 'Bolivia', 'Tanzania, United Republic of': 'Tanzania',
    'Moldova, Republic of': 'Moldova', 'Macedonia, the Former Yugoslav Republic of': 'North Macedonia',
    "Lao People's Democratic Republic": 'Laos', 'Brunei Darussalam': 'Brunei', 'Libyan Arab Jamahiriya': 'Libya',
    'Palestinian Territory, Occupied': 'Palestine', 'Congo, the Democratic Republic of the': 'Democratic Republic of the Congo',
    'USA': 'United States', 'UK': 'United Kingdom', 'Great Britain': 'United Kingdom', 'Holland': 'Netherlands',
}


def country_from_label(label):
    """Wikidata country name -> display name; '' for a former country; None if not recognized."""
    label = (label or '').strip()
    if label in WIKIDATA_NAMES:
        return WIKIDATA_NAMES[label]
    if label.casefold() in NATIONALITY:
        return NATIONALITY[label.casefold()]
    return None


def countries_from_nationality(text):
    """'Ghanaian' -> ['Ghana']; 'Chinese American' -> ['China', 'United States']; unknown -> []."""
    text = NATIVE_US.sub('American', re.sub(r'\(.*?\)|\S+ Clan.*', ' ', text or ''))
    text = re.sub(r'\b(born|active|citizen|resident|living|works|lives)\b.*', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip(' ,;.')
    if not text:
        return []
    if text.casefold() in NATIONALITY:
        return [NATIONALITY[text.casefold()]]
    # Compound nationalities: "Chinese American", "Japanese-born American", "Lebanese/French".
    words = [w for w in re.split(r'[\s/,;&]+|-(?!Guinean|Bissau)|\band\b', text) if w and w.casefold() not in
             {'born', 'of', 'descent', 'origin', 'heritage', 'naturalized', 'dual', 'citizenship'}]
    found, i = [], 0
    while i < len(words):
        # Try two-word names first ("South African", "New Zealander", "Puerto Rican").
        pair = ' '.join(words[i:i + 2]).casefold()
        if i + 1 < len(words) and pair in NATIONALITY:
            country, i = NATIONALITY[pair], i + 2
        elif words[i].casefold() in NATIONALITY:
            country, i = NATIONALITY[words[i].casefold()], i + 1
        else:
            return []
        if country not in found:
            found.append(country)
    # "African American" style: the second word names the country of citizenship.
    if len(found) == 2 and found[1] == 'United States' and text.casefold().startswith(('african', 'native')):
        return ['United States']
    return found
