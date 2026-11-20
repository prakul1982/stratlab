"""A theme's companies start from the exchange's own classification; the AI only adds on top (THEMES, owner 31 Oct: "the whole purpose
of themes is company discoverability and understanding of a sector"; "should we index every company with their own sector so no AI
issue?"). Live before this, "India Defence" showed 4 companies and left out 9: the AI decided who was in.

- The sector index: the screener's stored index (screens.load_index) already holds every listed company's official classification, from
  its stored page: India, NSE's macro-economic sector and basic industry (the exchange's four-level list; "Aerospace & Defense",
  "Ship Building & Allied Services", "Explosives"); the US, the SEC's SIC division and industry ("Semiconductors & Related Devices").
  Nothing more is read for it: the index is rebuilt with the company pages, so a new listing joins when its page is built. (A US
  company with no SIC code stored has no page built and no market value either, so it can't be shown in a theme yet.)
- The theme's industries (`industries_for`): a curated table for the usual themes and the page's suggestions; any other theme, the AI
  picks from the market's own list of industries (a name that isn't on it is dropped), kept a month in storage.
- Membership (`with_base`): every company in those industries is the base. The AI's map can sort a base company into one of its
  layers and show the words from its description, but a "no" from that check only moves it out of that layer, never out of the
  theme. Companies the AI names from other industries are the additions, checked against their own descriptions as before
  (theme_check.py): confirmed with the quote, or not yet confirmed; a clear "no" leaves an addition out.

No source is called here; every name and industry is the stored index's."""
import json
import math
import re
from datetime import datetime, timezone

# the version of the membership rules (who is in a theme, which industries, which layers): part of every cached read's key, so a read kept
# from before a deploy never keeps the old rules' companies or figures (R18: "Private banks" kept the public banks after the fix)
RULES = 77                       # e82 (LIVE18A-004/008, the R80 re-check: a bank's lending layer never a property layer (property_scope_layer, Regional banks' "Real estate-focused lenders (bank)"); a lender only on its principal words, never one phrase of a property owner's (Omega Healthcare, BREIT); a property owner never put in a layer of lenders on words shared (Pillarstone); a diversified owner of commercial property never in towers and data centres (Medalist, Presidio); a move for no stored figure no memory a later placement holds (Franklin BSP); a company left out of a renamed layer to the layer its words say (R80 Biotech)); e81 (LIVE17A-004, the R79 re-check: a kind of company a layer can never hold, whatever placed or held it there (kind_bars: a lender, InPoint, never in a layer of property owners; a non-traded REIT, BREIT, Hines, Ares, never in towers and data centres; KLX, a $21 m oilfield services company, never an integrated major; a property layer in a fertilizer theme only for companies whose own words say property is their business); a company placed by its words in the layer whose name it says, before a long description's many shared words (Medalist)); e80 (LIVE16A-002, the R78 re-check: XOM's "eighth-largest company by revenue", BP's "supermajors", Imperial Oil's "In Canada, it is a major producer", Suncor's and CrowdStrike's "It ..." lines, Wipro's "Wipro's services include", the encyclopedia's sentences run into a US company's words, never its own words (encyclopedia_sentence, the extract kept apart by the description reader)); e79 (the live R77 decks, LIVE15A-004/035: a company moved from "Other" into a layer and published there kept by a re-check only where the layer's test of what it sells, as now, doesn't say it sells something else, never by a line printing an act any trade does (came_from, OSI Systems' "designer"); an audit's quote of how a company is held or taxed no evidence against its layer (structure_quote, Essex's REIT tax election); an account of a company by a third party or of its history no line of its own words (_ACCOUNT); another company's sentences anywhere in its words left out (own_part, TOYO's Toyo Tire article)); e78 (the owner's review of the live R76 REITs deck: American Homes 4 Rent, "single-family homes as rental properties", and Essex Property Trust, "predominantly apartment communities", in "Other": a concept's words read with the company's name itself left out, never each word its name shares with them (layer_line, name_aside); a move out of a layer under an earlier name naming fewer kinds of property than its name now no finding on the layer as it is (narrower_name)); e77 (the live R76 Semiconductors deck: OSI Systems kept in "Fabless chip design" by a way of earning an answer read off its official industry, never said by its own words, which name security and inspection systems: model_said); R69 (lane r69e, the LIVE13A theme findings: a head naming an act any trade does ("design", "testing") said only with what it is done to, "vertically integrated" never the "integrated" of a name (sells_layer, ACT_HEADS); a company whose own words say it runs no business now in no layer of a business (business_moves); a former business no word of what it sells now (sold_text); a half of a layer split by market value judged as that layer for a company it takes from "Other", by the theme's own product named as what it makes where few of its companies say its name (sold_what, says_theme_product); an earlier re-check's move out of a layer undone only by words that say it; a move out judged by what it sells kept against its published layer under that layer's later name (hold_published)); R68 (lane r68e, the owner's review of the live R66 decks: a property owner's layer said by the kind of property its name and the company's own words name (theme_base.PROPERTY_TYPES, property_fit), never by a word they share; a rename of a property owner's layer to kinds most of its companies don't name not made (property_rename); a company whose own words name only kinds of property its layer's name doesn't moved to the layer that names its kind, else "Other", its words quoted (property_moves)); R67 (lane r67e, the owner's review of the live R65 decks: a kind of product a company's sentence names as what another product is for ("electrolyte salts for batteries") or after another product of its list is not its principal business, and the reason that screens it out quotes its own words, never another company's; a 10-K's sentences of how the company is held passed over and its list of what it owns read, a description of them alone read again); R66 (lane r66e, the LIVE12A theme findings: a stored description's opening sentences that speak of another company sharing the company's first word are not its words (theme_base.own_part, read by every reader of the stored descriptions); a dated head count, a rebranding or a listing line not a company's own words about its work; recycled, pre-owned or second-hand consumer goods say a resale layer); R65 (lane r65e, the live R64 decks' flags: a layer of one official industry none of whose companies' own words say its name not made, its companies in "Other"; a member whose own words say its layer never sent to "Other" for a figure it does not have; freight brokerage words (a logistics provider, third-party logistics, arranging shipments) say a layer of asset-light or freight brokers); R64 (lane r64e, the live R63 decks' flags: a layer whose name states distributors takes its distributors in its figures, a map pick whose own words, industry and name say no word of its layer not kept there on the map's pick alone); R63 (lane r63e, the R62 deck items and the live R62 decks' flags: a half of a layer split by market value renamed with its other half, a word put in place of one not plural singular, a member beyond the figures' window, no figure read for it, whose own words say its layer kept in it); R62 (lane r62, the owner's review of the live R60 decks: a company this placement puts into a named layer whose own words, industry and name say no word of it stays where it is published; a domestic filer never in a layer of foreign companies; an industry most of a layer's read companies share decides beside the company's words of the layer; members with no figure or description folded out of a layer mostly left out; "retail customers" names whom a company sells to; chips and semiconductors one concept); R60 (lane r60a, the owner's outside review of the live R59 decks: a layer the map named whose one company's own words say what it is kept with it, said to be one company and given no statistic; a company's words matched to a layer by its concept (LAYER_CONCEPTS: "direct-to-home" says satellite distribution) as well as its name's words; a way of earning never takes a company out of a layer its words name; a retail format apart from brand ownership; an established pharmaceutical company among biotechs in a layer of its own); R59 (lane r59, the flags left on the live R58.2 decks: a layer of four or more never mostly listed and left out of its figures, a company left out whose words print the layer's work counted on them and one whose words say none of its name not listed in it; a company moved in on no line of its words back where it was; a groups layer of two or fewer not made after every rule; the figures' window adds the companies whose lines say the layer first; a line's word the first the clause says); R58.2 (lane r582, the flags left on the live R58.1 decks: a layer of one company gains the companies whose words say its name or its company goes where its words say; the figures' window never prints a layer alone; a layer named by a way of earning none of its companies say not made; a name none of its companies' lines say gives way to one it had that they say; a company the words placement left in no layer before its words were stored placed by them; a map pick whose words name no other layer's business no longer "another business"; a name saying contract research read as project fees); R58.1 (lane r581, the open items after R58: a company the last re-check moved out of a layer new to it again; a rename that only adds words most of its largest companies don't say not made; a name none of whose words would stay kept with the word in brackets; a company kept in the theme on its words against one layer's answer quotes the words); R58 (lane r58, the owner's review of the live R57.2 decks: a layer an earlier published version had counts as published and keeps its name; a one-company layer of the published version stays when its member's words say its name; a layer joining a large and a small scale split by scale; a computing layer made by how companies earn not made in a theme that names no computing; a name none of its companies say takes their word in place); R57.2 (lane r572, the live R57.1 decks: a member the map placed in a layer whose own words don't contradict it in the layer's figures, the largest never left out on insufficient evidence alone, a layer whose name states its way of earning read that way, a removal on one layer's answer decided by the company's own words); R57.1 (lane r571, the live R57 decks: the peer pull off, a check's "verified" never vouching for a layer it wasn't asked about, a renamed published layer kept, a published member outside the map's groups kept, 3M out, no thin groups layer, the audit's old quote read like a stable placement); R56 (lane p57, the owner's review of the live R56 decks: the placement contract, theme_base.keep_published, hold_published, truthful_layers, best_layer_moves; theme_check.check_placements `held`); R55 (lane t56, the owner's review of the live R55 decks, proven on exact replays of the live R55 placement inputs): the taxonomy guard is the last step of the placement, after every rule that moves companies: against the previous published version (previous_published: the stored snapshot, and for a layer it already lost the moves of the one re-check that removed it, theme_changes.lost_moves; c54 read every logged move back, so the R54 restore's own moves into "Aluminium" counted its companies as of "Other" and the layer was lost again), a named layer of five or more companies that is gone comes back with its companies whose own words or official industry still say what it sells, from "Other" or from a layer a later rule put them in without a recorded reason (restore_vanished: Metals "Aluminium" 13, Manaksia Aluminium back from the steel pipe makers; Consumer retail "Catalog and mail-order houses" 6), a layer whose companies went to layers new to this version is renamed, not lost, and a fall of five points or more in the informative share sends back to their layer the companies of "Other" whose own words still say what it sells (share_guard); R54 (lane v55, the owner's review of the live R54 decks, proven on exact replays of the live R54 placement inputs): theme membership decided before any layer: a company the theme's official industry brought in whose principal business is a kind of product the theme's definition doesn't include is screened out with that reason, never kept in "Other" (theme_check.off_scope, without_off_industry `scope`: Indo National out of FMCG); a commercial-stage company is displayed in the map's commercial layer, never in one named by a development stage, and the other way round (stage_moves: Merck and Novartis out of "Pipeline-stage and royalty-funded drug developers"); a contract manufacturer or component supplier of the theme's products left in "Other" goes to a layer of that kind named from the theme's words, two or more, else is said to be one (fallback_layer: UFP Technologies and Integer Holdings in "Medical device contract manufacturers"); R53 (lane c54, the owner's review of the live R53 decks, proven on exact replays of the live R53 placement inputs): a company new to a layer named by what it sells (its previous live layer another, or the stored change log says a re-check moved it there) joins it only on evidence that it sells what the name defines, read in the sentences of its own words that say what it does or in its official industry's name (sells_layer, sold_what: Intel out of "Chip equipment and subsystem suppliers", Indo National out of "Branded packaged foods manufacturing", UFP Technologies out of "Surgical robotics systems"), else back where it came from; a named layer of five or more companies the previous live version had is restored with those of its companies that still fit when a re-check would leave it with none (restore_vanished: Metals "Aluminium"); R52 (lane d53, the owner's review of the live R52 decks, proven on the exact replay of the live R52 Consumer retail placement inputs): a company an earlier stored version of the theme dropped as another business stays out while no words of its own are read (without_off_industry `before`, theme_changes.off_memory), and one its words now keep in is named ("back"); every name a layer had is kept ("aka", theme_data.same_names); R51 (lane gl52, the rotating review of Release 51, proven on exact replays of its live placement inputs): a company with words that state no way of earning, or none, is in its layer's figures on its industry when that is the industry most of the layer's companies shown to earn its way share (its own other half by market value is no other layer) or the one the layer's own name names (by_model on_ind); a medical laboratory's or hospital's industry states its way of earning over an answer of a service, seller or software family or of low confidence (industry_model); a company read only weakly whose own words say the layer's name and its way of earning is in its figures on its words; a payments processor's model (payments); a layer whose name states EPC takes an EPC contractor in its figures (NAME_PART_MODEL); an AI placement or map pick whose words and industry are of another layer and not its own is listed but left out of its figures (definition_fit "unfit"); words any company uses and the customers a description names are no fit to a layer (GENERIC_FIT, _CUSTOMERS, _CONTRAST); the walk back for an earlier answer of the same map reads every carried version (theme_routes.kept_placement, fill_earlier); R50 (lane rv51, the outside review of the live Release 49 decks: the IT services placement asked for 2 new companies replaced the kept answer's layer names and its two extra layers, 139 companies in informative layers became 132; proven on the exact replay of the live Release 49 placement inputs): an answer for companies a kept answer didn't place only adds names and extra layers (with_earlier), and the kept answer takes those an earlier answer of the same map gave and it lacks (theme_routes.kept_placement); R49 (lane gl50, the rotating review of six unseen themes): a company whose own words and official industry fit neither what its layer is (its name and description) moves to the one layer its words say, else the one its industry is named by, else "Other", with the reason (definition_fit); every company still without a model is asked in batches on each check (reask_unknown, any placement version) and one whose words state it takes it (stated_for_rest); one with no words of a layer's majority industry is in its figures on its industry when no other layer has that industry as its majority (by_model on_ind); R48 (lane ex49, the outside review of the live Release 48 Consumer retail deck: lululemon in "Apparel and consumer brand owners" by its own words, left out of its figures as "another business"; proven on the exact replay of the live Release 46 placement inputs, where it is the one company of the 14 themes whose place in its layer's figures changes): a company read as a retailer whose own words say it designs the goods it sells (or makes them under its own brand), that the answer also read as a maker, and whose words say its layer's name, is in a layer of makers' figures (by_model `own_goods`); each company left out of a layer's figures carries why, precisely (by_model `out_why`: another business than its industry, another way of earning, how it earns read only weakly, no description of its own, words that don't state how it earns); R47 (lane cl48, the outside review of the live Release 46 Consumer retail deck: a designer of branded athletic apparel in "Off-price, dollar and discount store chains"; proven on the exact replay of the live Release 46 placement inputs): a company leaving a map layer by how it earns joins the largest layer of its family by default only when its own words say that layer's name or the name states no kind of business; else the map's layer it is in when its words say that layer's name (out of its figures), else a layer of its family sharing two of its words, else "Other" (by_model.home_of); a compound of a short word ("off-price") is one word in a layer's words, so "branched off" says nothing of it (whole_stems, says_most_of); a company listed in a layer as another way of earning is said to earn another way, never to have evidence that doesn't show how it earns (out_line); an industry of a replaced AI pick most of whose companies were in informative layers stays in the new pick (industries_for `held`); R46 (lane cv47, the live Release 46 Utilities deck: the cable and electrical equipment makers' layers formed on every replay but never on live, proven on the exact replay of the live Release 46 placement inputs, which carry each company's stored facts): the titles of a company's filings ("From its own filings: ...") are no words of its own (own_text), so their "own" no longer says "Makers of their own products" and keeps a cable maker out of its industry's layer (from_other 3); R45 (lane tx2, the outside review of the live Release 45 decks: Bosch and Asahi India Glass out of the component suppliers' layer; proven on the exact replay of the live Release 45 Automotive placement inputs): a company leaves a map layer mostly of its industry for another layer of its industry only on evidence of that layer (its own words say its name, or it holds a larger share of its industry: by_model evidence_for); the previous live placement of the same map (theme_changes' snapshot, place_rest `previous`) is kept by a company the split would move out of it with no evidence of the new layer, and by an unchecked map pick with no evidence of the layer it is in (held_to_previous); R44 (lane c1, the outside review of the live Release 43 decks, proven on the exact replay of its placement inputs): the companies left in "Other" placed only by their own words or official industry (theme_base.from_other: a layer whose name says all their industry says, the one layer of their way of earning whose name their words say two or more and half of the words of, a layer of one official industry made of them and of those the split moved by how they earn alone: ferro alloy, aluminium product, cable and electrical equipment makers), a map pick from another industry whose words say its layer's name is confirmed by them (confirmed_by_words: PB Fintech), a sportsbook, broadcast network, enterprise software house, VR concert producer and diversified holding company filed as retail are another business; R43 (lane d1, the outside review of the live Release 41 decks, proven on the exact replay of its placement inputs): a company the map named in a layer whose way of earning no layer of the map has stays in that layer, out of its figures (Arm, Fortinet); the largest layer of a family whose name states a kind of business the company's words don't say takes it by industry only as the family's catch-all, and such companies of one official industry with the like of them in "Other" make a layer of that industry (the apparel chains); a company named in a sub-theme only is placed like the theme's own; a company in no layer with no words of its own is "not checked yet" ("unread"); a weak-evidence company of the layer's industry is in its figures on its industry (Mahindra & Mahindra); pawnbrokers, IT resellers to business, blank-check companies, banks, payments and travel firms filed as retail are another business; "real estate development" is a developer's words; a maker read as a telecom operator makes its own products; R40 (lane s3-r40, the owner's review of the live Release 39 decks, proven on the exact replay of its placement inputs): a layer whose shown name states two ways of earning takes a company of either that holds its industry and whose words say what its name says (online sellers into "Online retailers and marketplaces"); a company the theme's industry brought in whose own words describe another business is dropped from the theme and named on its coverage (propane distributors under retail, solar makers under semiconductors: theme_base.without_off_industry); in a layer of one official industry a company of the layer's kin of making is in its figures (Bosch, Asahi India Glass: by_model KIN_FAMILIES); a layer the split named only by how its companies earn is never ranked ("by_how"); R41 (lane s2-exact, exact replays of the live Release 38.1 placement from its placement inputs): a company leaving a map layer by how it earns stays in it, out of its figures, when that layer is mostly of its industry and no layer of its family is (Bosch, Asahi India Glass); a layer whose name states another way of earning is not the map's layer of a company's industry, and the largest stands by default only as its family's catch-all (online sellers in "Off-price"); a company the split by model moved joins a map layer in 3b only when it fits (Qorvo in "Semiconductor equipment"); a model asked apart from the placement moves no company out of the map layer the placement put it in, and an answer carried from earlier rules sticks: nothing it answered is asked again (place_rest `carried`; Hikal and Brooks); R38.1: a kept placement carried back through every version that kept none of its own (theme_routes.placed), past 39's placements asked again from nothing; R38 (lane s1-fit, the outside review of the live R37 decks: 34 companies moved into "Off-price, dollar and value-format retailers", Micron, Intel and SK Hynix into "Semiconductor equipment"): a company leaving "Other" that the largest layer of its family neither holds by industry nor by words goes to the layer of its family that fits it, else stays in "Other", never the largest by default; a split-made layer joins a map layer of the same model only with the companies whose words fit it (by_model.home_of, fits). R37 (lane r2, the owner: misclassifications across all themes): a company no answer gave a model takes the one its own words state in so many words, read since (theme_check.stated_model, refine_kept), a bank's or lender's industry is lending, a landlord's own words make it one whatever its industry, OSAT and ESDM words are contract making, own-fab words read in an annual report make a chip maker no fabless one, a company leaving "Other" joins the largest layer of its family only when that holds its industry or words, else a layer all of its industry sharing its words, else stays in "Other" when no layer holds either (by_model.home_of), a contract maker joins only a contract layer of its kind (theme_check.contract_kind), a company the map placed whose model only its words state stays in its layer (by_model settled); R36 (GPT review of the live R35 decks): foundry words with products of its own named are no contract maker's and a chip maker naming its own products given contract manufacturing is a maker (theme_check.chip_idm), chips made using specialty process technologies are a foundry's, a seller of its own goods given platform is a retailer, a company of another business filed under the theme's industry (solar under semiconductors) stays in "Other" (theme_check.off_industry), a company leaving a map layer for its family goes to the family's layer of its own industry (by_model); q1: a network operator given software or capacity is telecom_services (theme_check.telecom_operator), a rule-made model of another family not held at the answer's "low" (said_for), foundry words read in a 10-K/20-F as contract making; lane n2: a kept model of low confidence read again from the evidence as it is now (refine_kept), foundry words as contract making, family words (theme_check.model_confidence), retail vs platform (refine_model); R34: the model rules that changed after R33 (a chip materials supplier is an ingredient maker; a model-named layer joins a map layer only when one layer has its model) apply to every kept check, placement and dive: whenever refine_model, by_model or a model rule changes, bump this; R33: a company with no model takes the one its map layer's name states (models_from_layer); R32: chip designers without fabs as fabless (theme_check.chip_designer), a layer named by how it earns joins the map's layer of its primary model, a market-value half with no shown company undone (unsplit_unshown); R31: lenders apart from developers and landlords, fabless vs IDM by owned fabs (theme_check.refine_model), a metals family's commodity as its sub-basis, a split-made layer of one primary model joins the map's (by_model 3b); R30: a kept placement's unknown models asked again once the companies' descriptions are kept (reask_unknown); R29: kinds of utility and of metals business as their own models (theme_check.refine_model); R21: every confirmed company in one of the map's layers (place_rest); R22: layer names fit, currencies, extra layers; R25: one revenue model a layer; R26: models from more evidence and checked by it, names after the split; R27: primary model, tags and confidence, comparable segments, no one-company layer; R28: the companies to place carry their own descriptions (theme_routes.describe_unplaced)
INDUSTRIES_DAYS = 30            # the AI's pick of a free-text theme's industries is made again after this long (at most monthly)
PICK_RULES = 45                 # cv47 (R46): the rules version the AI's industry pick (PICK_SYSTEM, ai_pick) last changed under: a pick kept under it or later rules is kept; bump to RULES only when the pick itself changes
FIGURES_MAX = 100               # companies the dive works figures out for: every one the AI named, then the largest of the base (R31: 60 -> 100; stored reads only, the deck built in under a second for 100 synthetic companies, the sector-figure worker bounded by its queue)
WINDOW_LAYER_MIN = 3             # r582: a named layer the figures' window holds fewer companies of gains its next largest, up to this many (a median's MIN_BASE)
DESCRIBE_MAX = 120              # base companies whose own one-line description is looked up for the page, largest first

# The usual themes and the page's suggestions: the official industries at their core. `words`: a theme naming any of them (or a
# phrase) has these industries; `unless`: a phrase that means a narrower theme with its own entry. A market with no list here is left to
# the AI's pick; an empty list says no official industry is the theme's core (a narrow theme inside a wide industry).
CONCEPTS = [
    {"words": {"defence", "defense", "military", "missile", "warship", "armament", "ammunition", "munition", "drone", "aerospace"},
     "IN": ["Aerospace & Defense", "Ship Building & Allied Services", "Explosives"], "IN_named": ["BEML"],
     "US": ["Guided Missiles & Space Vehicles & Parts", "Ordnance & Accessories, (No Vehicles/Guided Missiles)",
            "Search, Detection, Navigation, Guidance, Aeronautical Sys", "Aircraft Engines & Engine Parts",
            "Aircraft Parts & Auxiliary Equipment, Nec", "Ship & Boat Building & Repairing", "Aircraft"]},
    {"words": {"shipbuilding", "shipyard", "shipbuilder"}, "IN": ["Ship Building & Allied Services"], "US": ["Ship & Boat Building & Repairing"]},
    {"words": {"railway", "rail", "railroad", "train", "metro"}, "IN": ["Railway Wagons"],
     "IN_named": ["RVNL", "IRCON", "IRFC", "RITES", "IRCTC", "RAILTEL", "BEML", "CONCOR", "KERNEX"],
     "US": ["Railroads, Line-Haul Operating", "Railroad Equipment"]},
    {"words": {"ev", "evs"}, "phrases": ("electric vehicle", "electric vehicles", "electric mobility", "e mobility", "electric cars",
                                        "electric two wheelers", "electric scooters"),
     "IN": ["Passenger Cars & Utility Vehicles", "2/3 Wheelers", "Commercial Vehicles", "Auto Components & Equipments"],
     "US": ["Motor Vehicles & Passenger Car Bodies", "Motor Vehicle Parts & Accessories"]},
    {"words": {"auto", "automobile", "automotive", "car", "carmaker", "vehicle"}, "phrases": ("two wheelers",),
     "unless": ("ev", "evs", "electric vehicle", "electric vehicles", "electric cars", "electric two wheelers", "electric scooters"),
     "IN": ["Passenger Cars & Utility Vehicles", "2/3 Wheelers", "Commercial Vehicles", "Tractors", "Auto Components & Equipments",
            "Tyres & Rubber Products"],
     "US": ["Motor Vehicles & Passenger Car Bodies", "Motor Vehicle Parts & Accessories", "Tires & Inner Tubes", "Truck & Bus Bodies"]},
    # India's "Power Generation" mixes coal and gas plants with solar and wind ones, and the module and turbine makers sit in wide electrical
    # industries: India's renewables are a named list only, so a thermal-only company is out unless the AI names it (THEMES, 4 Nov)
    {"words": {"renewable", "solar", "wind"}, "phrases": ("clean energy", "green energy", "green power"),
     "IN": [], "IN_named": ["WAAREEENER", "PREMIERENE", "SUZLON", "INOXWIND", "KPIGREEN", "NTPCGREEN", "ADANIGREEN", "TATAPOWER", "ACMESOLAR",
                            "SJVN", "NHPC", "JSWENERGY", "EMMVEE", "VIKRAMSOLR", "SAATVIKGL", "WAAREERTL", "WEBELSOLAR", "BORORENEW", "INOXGREEN",
                            "SWSOLAR", "CLEANMAX", "IREDA"],
     "US": ["Cogeneration Services & Small Power Producers"],
     "US_named": ["NEE", "FSLR", "ENPH", "NXT", "BEP", "BEPC", "CWEN", "ORA", "SEDG", "RUN", "SHLS", "FLNC", "ARRY", "CSIQ", "JKS"]},
    {"words": {"electricity", "grid", "electrification", "utility", "utilities"}, "phrases": ("power sector", "power utilities", "power transmission"),
     "IN": ["Power Generation", "Integrated Power Utilities", "Power - Transmission", "Power Distribution", "Power Trading",
            "Heavy Electrical Equipment", "Cables - Electricals"],
     "US": ["Electric Services", "Electric & Other Services Combined", "Switchgear & Switchboard Apparatus", "Electrical Industrial Apparatus",
            "Motors & Generators", "Drawing & Insulating Of Nonferrous Wire", "Water, Sewer, Pipeline, Comm & Power Line Construction"]},
    {"words": {"bank", "banking"}, "IN": ["Private Sector Bank", "Public Sector Bank", "Other Bank"],
     "US": ["National Commercial Banks", "State Commercial Banks", "Commercial Banks, Nec", "Savings Institution, Federally Chartered",
            "Savings Institutions, Not Federally Chartered"]},
    {"words": {"nbfc", "lending", "lender", "microfinance"}, "phrases": ("housing finance", "consumer finance"),
     "IN": ["Non Banking Financial Company (NBFC)", "Housing Finance Company", "Microfinance Institutions", "Financial Institution"],
     "US": ["Personal Credit Institutions", "Short-Term Business Credit Institutions", "Miscellaneous Business Credit Institution",
            "Mortgage Bankers & Loan Correspondents"]},
    # the US files card networks and payment processors under wide service codes: named
    {"words": {"payment", "fintech", "upi"}, "IN": ["Financial Technology (Fintech)"],
     "US": [], "US_named": ["V", "MA", "PYPL", "AXP", "FIS", "GPN", "XYZ", "AFRM", "TOST", "FOUR", "COIN"]},
    {"words": {"insurance", "insurer"}, "IN": ["Life Insurance", "General Insurance", "Insurance Distributors"],
     "US": ["Life Insurance", "Fire, Marine & Casualty Insurance", "Accident & Health Insurance", "Insurance Agents, Brokers & Service",
            "Surety Insurance", "Title Insurance", "Insurance Carriers, Nec"]},
    {"words": {"broking", "broker", "exchanges", "amc", "depository"}, "phrases": ("capital markets", "capital market", "asset management", "wealth management"),
     "IN": ["Asset Management Company", "Stockbroking & Allied", "Exchange and Data Platform", "Depositories, Clearing Houses and Other Intermediaries",
            "Other Capital Market related Services", "Ratings", "Financial Products Distributor"],
     "US": ["Security Brokers, Dealers & Flotation Companies", "Security & Commodity Brokers, Dealers, Exchanges & Services", "Investment Advice"]},
    {"words": {"pharma", "pharmaceutical", "drug", "drugmaker", "medicine", "generic", "biotech", "biotechnology"},
     "unless": ("glp 1", "obesity"),
     "IN": ["Pharmaceuticals", "Biotechnology"],
     "US": ["Pharmaceutical Preparations", "Biological Products, (No Diagnostic Substances)", "Medicinal Chemicals & Botanical Products",
            "In Vitro & In Vivo Diagnostic Substances"]},
    # a narrow theme inside a wide industry (no official industry is its core): the theme's own companies, named, so it never rests on the
    # AI alone (THEMES, 4 Nov: "every curated theme has a base")
    {"words": {"glp"}, "phrases": ("glp 1", "obesity drugs", "weight loss drugs"),
     "IN": [], "IN_named": ["SUNPHARMA", "DRREDDY", "BIOCON", "ZYDUSLIFE", "LUPIN", "MANKIND", "CIPLA", "GLENMARK", "DIVISLAB"],
     "US": [], "US_named": ["LLY", "NVO", "AMGN", "VKTX", "PFE", "BDX", "WST", "TMO", "STVN", "HIMS", "ALT", "GPCR"]},
    {"words": {"hospital", "healthcare", "diagnostic", "medtech"}, "phrases": ("medical devices",),
     "IN": ["Hospital", "Healthcare Service Provider", "Medical Equipment & Supplies", "Healthcare Research, Analytics & Technology"],
     "US": ["Services-General Medical & Surgical Hospitals, Nec", "Services-Hospitals", "Services-Medical Laboratories",
            "Surgical & Medical Instruments & Apparatus", "Electromedical & Electrotherapeutic Apparatus"]},
    {"words": {"software", "saas"}, "phrases": ("it services", "indian it", "information technology"),
     "IN": ["Computers - Software & Consulting", "Software Products", "IT Enabled Services"],
     "US": ["Services-Prepackaged Software", "Services-Computer Programming Services", "Services-Computer Integrated Systems Design",
            "Services-Computer Processing & Data Preparation", "Services-Computer Programming, Data Processing, Etc."]},
    # the SEC files solar-cell and inverter makers under semiconductors (SIC 3674): they are renewables' named list, not the chip base;
    # the chip-equipment makers and Qualcomm file under other codes
    {"words": {"semiconductor", "chip", "chipmaker", "foundry"}, "IN": [], "IN_named": ["CGPOWER", "KAYNES", "MOSCHIP", "ASMTEC", "RIR", "TATAELXSI"],
     "US": ["Semiconductors & Related Devices"],
     "US_named": ["ASML", "LRCX", "KLAC", "QCOM", "TER", "ENTG"], "US_except": ["FSLR", "ENPH", "NXT", "SEDG", "SHLS", "ARRY", "CSIQ", "JKS"]},
    {"words": {"cybersecurity"}, "phrases": ("cyber security",), "IN": [], "IN_named": ["QUICKHEAL"],
     "US": [], "US_named": ["CRWD", "PANW", "FTNT", "ZS", "OKTA", "S", "CHKP", "NET", "TENB", "RPD", "QLYS", "VRNS", "GEN", "AKAM"]},
    {"words": {"datacenter", "datacentre"}, "phrases": ("data center", "data centers", "data centre", "data centres"),
     "IN": [], "IN_named": ["ANANTRAJ", "NETWEB", "TECHNOE", "TATACOMM", "BLUESTARCO", "BHARTIARTL"],
     "US": [], "US_named": ["EQIX", "DLR", "IRM", "NVDA", "AMD", "AVGO", "ANET", "VRT", "ETN", "SMCI", "DELL", "APLD", "CORZ", "CRWV", "NBIS"]},
    {"words": {"nuclear", "uranium", "smr"}, "IN": [], "IN_named": ["NTPC", "LT", "BHEL", "WALCHANNAG", "MTARTECH", "HCC"],
     "US": [], "US_named": ["CEG", "VST", "TLN", "CCJ", "OKLO", "SMR", "NNE", "BWXT", "LEU", "UEC", "GEV", "NXE", "DNN"]},
    {"words": {"telecom", "telecommunication", "5g"},
     "IN": ["Telecom - Cellular & Fixed line services", "Telecom - Infrastructure", "Telecom - Equipment & Accessories", "Other Telecom Services"],
     "US": ["Radiotelephone Communications", "Telephone Communications (No Radiotelephone)", "Communications Services, Nec", "Telephone & Telegraph Apparatus"]},
    {"words": {"cement"}, "IN": ["Cement & Cement Products"], "US": ["Cement, Hydraulic"]},
    {"words": {"steel"}, "IN": ["Iron & Steel", "Iron & Steel Products", "Sponge Iron", "Pig Iron"],
     "US": ["Steel Works, Blast Furnaces & Rolling Mills (Coke Ovens)", "Steel Works, Blast Furnaces & Rolling & Finishing Mills", "Steel Pipe & Tubes"]},
    {"words": {"mining", "mine", "miner", "metal", "aluminium", "aluminum", "copper", "zinc", "coal"},
     "IN": ["Coal", "Aluminium", "Copper", "Zinc", "Diversified Metals", "Industrial Minerals", "Ferro & Silica Manganese"],
     "US": ["Metal Mining", "Miscellaneous Metal Ores", "Bituminous Coal & Lignite Surface Mining", "Primary Production Of Aluminum",
            "Mining & Quarrying Of Nonmetallic Minerals (No Fuels)"]},
    {"words": {"gold", "silver"}, "phrases": ("precious metals",), "IN": ["Precious Metals"], "US": ["Gold And Silver Ores", "Silver Ores"]},
    {"words": {"oil", "petroleum", "refining", "refinery", "lng", "cng", "upstream"}, "phrases": ("oil and gas", "natural gas", "city gas"),
     "IN": ["Oil Exploration & Production", "Refineries & Marketing", "LPG/CNG/PNG/LNG Supplier", "Gas Transmission/Marketing",
            "Oil Equipment & Services", "Offshore Support Solution Drilling", "Oil Storage & Transportation"],
     "US": ["Crude Petroleum & Natural Gas", "Petroleum Refining", "Drilling Oil & Gas Wells", "Oil & Gas Field Services, Nec",
            "Oil & Gas Field Machinery & Equipment", "Natural Gas Transmission", "Natural Gas Distribution", "Pipe Lines (No Natural Gas)"]},
    {"words": set(), "phrases": ("specialty chemicals", "speciality chemicals"), "IN": ["Specialty Chemicals"],
     "US": ["Industrial Organic Chemicals", "Miscellaneous Chemical Products", "Chemicals & Allied Products"]},
    {"words": {"chemical", "agrochemical", "petrochemical"}, "unless": ("specialty chemicals", "speciality chemicals"),
     "IN": ["Specialty Chemicals", "Commodity Chemicals", "Petrochemicals", "Dyes And Pigments", "Pesticides & Agrochemicals", "Industrial Gases"],
     "US": ["Industrial Organic Chemicals", "Industrial Inorganic Chemicals", "Chemicals & Allied Products",
            "Plastic Materials, Synth Resins & Nonvulcan Elastomers", "Agricultural Chemicals"]},
    {"words": {"fertiliser", "fertilizer"}, "IN": ["Fertilizers"], "US": ["Agricultural Chemicals"]},
    {"words": {"fmcg", "staples"}, "phrases": ("consumer staples", "packaged food", "packaged foods"),
     "IN": ["Diversified FMCG", "Personal Care", "Packaged Foods", "Household Products", "Dairy Products", "Other Food Products", "Edible Oil",
            "Tea & Coffee", "Cigarettes & Tobacco Products", "Other Beverages"],
     "US": ["Food And Kindred Products", "Perfumes, Cosmetics & Other Toilet Preparations", "Soap, Detergents, Cleang Preparations, Perfumes, Cosmetics",
            "Beverages", "Bottled & Canned Soft Drinks & Carbonated Waters", "Cigarettes"]},
    {"words": {"realty", "reit", "property", "housing"}, "phrases": ("real estate",), "unless": ("housing finance",),
     "IN": ["Residential, Commercial Projects", "Real Estate related services", "Real Estate Investment Trusts (REITs)"],
     "US": ["Real Estate Investment Trusts", "Operative Builders", "Real Estate", "Real Estate Operators (No Developers) & Lessors"]},
    {"words": {"infrastructure", "infra", "construction", "road", "highway"},
     "IN": ["Civil Construction", "Road AssetsToll, Annuity, Hybrid-Annuity"],
     "US": ["Heavy Construction Other Than Bldg Const - Contractors", "Water, Sewer, Pipeline, Comm & Power Line Construction",
            "Construction - Special Trade Contractors"]},
    {"words": {"hotel", "tourism", "travel", "hospitality"}, "IN": ["Hotels & Resorts", "Tour, Travel Related Services"],
     "US": ["Hotels & Motels", "Hotels, Rooming Houses, Camps & Other Lodging Places"]},
    {"words": {"aviation", "airline", "airport"}, "IN": ["Airline", "Airport & Airport services"],
     "US": ["Air Transportation, Scheduled", "Airports, Flying Fields & Airport Terminal Services", "Air Transportation, Nonscheduled"]},
    {"words": {"logistics", "shipping", "port", "freight"}, "IN": ["Logistics Solution Provider", "Shipping", "Port & Port services", "Road Transport"],
     "US": ["Trucking (No Local)", "Arrangement Of Transportation Of Freight & Cargo", "Deep Sea Foreign Transportation Of Freight", "Air Courier Services"]},
    {"words": {"media", "entertainment", "broadcasting", "film"},
     "IN": ["Media & Entertainment", "TV Broadcasting & Software Production", "Film Production, Distribution & Exhibition", "Digital Entertainment",
            "Electronic Media", "Print Media"],
     "US": ["Cable & Other Pay Television Services", "Television Broadcasting Stations", "Services-Motion Picture & Video Tape Production"]},
    {"words": {"water"}, "IN": ["Water Supply & Management"], "US": ["Water Supply"]},
]


# the exchange's industry names as a layer shows them (R20, the owner: "Computer Peripheral Equipment, Nec" and "Services-Prepackaged Software" as
# layer names): the common ones by a plain name, any other cleaned (no "Services-" prefix, no "Nec", no "(No ...)", "&" for "And")
PLAIN_INDUSTRY = {
    "services-prepackaged software": "Software", "services-computer programming services": "IT services",
    "services-computer integrated systems design": "IT services", "services-computer programming, data processing, etc.": "IT services",
    "services-computer processing & data preparation": "Data processing", "computer peripheral equipment, nec": "Computer hardware",
    "electronic computers": "Computer hardware", "computer communications equipment": "Networking equipment",
    "computer storage devices": "Computer hardware", "semiconductors & related devices": "Semiconductors",
    "services-business services, nec": "Business services", "telephone communications (no radiotelephone)": "Telecom services",
    "radiotelephone communications": "Wireless telecom", "pharmaceutical preparations": "Pharmaceuticals",
    "biological products, (no diagnostic substances)": "Biotech products", "in vitro & in vivo diagnostic substances": "Diagnostics",
    "national commercial banks": "Commercial banks", "state commercial banks": "Commercial banks", "commercial banks, nec": "Commercial banks",
    "motor vehicles & passenger car bodies": "Vehicle makers", "motor vehicle parts & accessories": "Vehicle parts",
    "crude petroleum & natural gas": "Oil and gas producers", "petroleum refining": "Refining", "electric services": "Electric utilities",
    "real estate investment trusts": "REITs", "retail-eating places": "Restaurants", "services-medical laboratories": "Medical laboratories",
    "surgical & medical instruments & apparatus": "Medical instruments", "electromedical & electrotherapeutic apparatus": "Medical devices",
    "aircraft parts & auxiliary equipment, nec": "Aircraft parts", "guided missiles & space vehicles & parts": "Missiles and space",
    # India's exchange names where a plainer word says the same (R21: "Computers - Software & Consulting" as a layer)
    "computers - software & consulting": "IT services", "it enabled services": "IT-enabled services", "software products": "Software products",
    "passenger cars & utility vehicles": "Cars and utility vehicles", "2/3 wheelers": "Two- and three-wheelers", "auto components & equipments": "Auto components",
    "tyres & rubber products": "Tyres", "private sector bank": "Private banks", "public sector bank": "Public sector banks",
    "non banking financial company (nbfc)": "Non-bank lenders (NBFC)", "aerospace & defense": "Aerospace and defence",
    "ship building & allied services": "Shipbuilding", "telecom - cellular & fixed line services": "Telecom services",
    "residential, commercial projects": "Real estate developers", "road assetstoll, annuity, hybrid-annuity": "Road assets",
    # c1 (R44): names a layer of one official industry shows (theme_base.from_other)
    "cables - electricals": "Electrical cables", "ferro & silica manganese": "Ferro alloys",
}


def plain_industry(name) -> str:
    """An official industry's name as a layer shows it: the common ones by a plain name (PLAIN_INDUSTRY), any other cleaned. Both markets."""
    raw = " ".join(str(name or "").split())
    if not raw:
        return raw
    hit = PLAIN_INDUSTRY.get(raw.lower())
    if hit:
        return hit
    t = re.sub(r"^services-\s*", "", raw, flags=re.I)
    t = re.sub(r",?\s*\bnec\b\.?", "", t, flags=re.I)
    t = re.sub(r",?\s*\((?:no|not|except)\b[^)]*\)", "", t, flags=re.I)
    t = re.sub(r"\s+and\s+", " & ", t, flags=re.I).strip(" ,-")
    if t.isupper() or t.islower():
        t = t.title()
    return t or raw


def industry_label(name) -> str:
    """An official industry as the name of a layer of its companies (d1): its plain name without the SEC's "Retail-" kind of prefix, in
    sentence case ("Retail-Family Clothing Stores" -> "Family clothing stores")."""
    t = re.sub(r"^[A-Za-z]+-\s*(?=[A-Z])", "", plain_industry(name)).replace(" & ", " and ")
    if not t:
        return t
    # fix20 (LIVE14B-005, the IT services sample deck: a layer "It services"): a word in capitals of the industry's own name (IT, BPO, EMS,
    # LPG) keeps them; any other word is lower case after the first
    caps = not plain_industry(name).isupper()

    def part(w: str, first: bool) -> str:
        if caps and len(w) >= 2 and w.isupper() and w.isalpha():
            return w
        return w[:1].upper() + w[1:].lower() if first else w.lower()
    return " ".join("-".join(part(p_, i == 0 and j == 0) for j, p_ in enumerate(w.split("-"))) for i, w in enumerate(t.split(" ")))


def key(name) -> str:
    """An industry name as compared: case and spacing aside (the SEC writes "Drawing & Insulating Of  Nonferrous Wire")."""
    return " ".join(str(name or "").split()).lower()


def _words(theme: str) -> tuple[str, set[str]]:
    t = " " + " ".join(re.findall(r"[a-z0-9]+", str(theme or "").lower())) + " "
    words = set(t.split())
    words |= {w[:-1] for w in list(words) if w.endswith("s") and len(w) > 3}        # "banks", "railways", "chips"
    return t, words


def concepts_of(theme: str) -> list[dict]:
    """The curated entries a theme names."""
    t, words = _words(theme)
    out = []
    for c in CONCEPTS:
        if any(f" {p} " in t for p in c.get("unless", ())):
            continue
        if words & c["words"] or any(f" {p} " in t for p in c.get("phrases", ())):
            out.append(c)
    return out


def known_industries(rows: list[dict]) -> dict[str, str]:
    """{key: the industry as the list writes it} for every industry in the market's index."""
    out = {}
    for r in rows or []:
        i = str(r.get("industry") or "").strip()
        if i:
            out.setdefault(key(i), i)
    return out


def named_lists(region: str, theme: str) -> tuple[list[str], list[str]]:
    """(symbols the curated table names as the theme's own, symbols it keeps out of the industry base unless the AI names them)."""
    named, out = [], []
    for c in concepts_of(theme):
        named += [s for s in c.get(f"{region}_named", []) if s not in named]
        out += [s for s in c.get(f"{region}_except", []) if s not in out]
    return named, [s for s in out if s not in named]


def curated(region: str, theme: str, known: dict[str, str]) -> list[str] | None:
    """The curated industries for a theme in a market (as the index writes them), or None when the table has no entry for it there."""
    lists = [c[region] for c in concepts_of(theme) if region in c]
    if not lists:
        return None
    out = []
    for names in lists:
        for n in names:
            got = known.get(key(n))
            if got and got not in out:
                out.append(got)
    return out


PICK_SYSTEM = """You map a market theme to the stock exchange's official industry classification. From the LIST of industries given (the
exchange's own names), pick the industries whose listed companies, nearly all of them, do the theme's core work. Pick none when every
industry on the list is much wider than the theme (a single product, a drug class, a technology inside a wider industry). Copy each
name exactly as it is on the list. At most 6.
Reply with ONLY this JSON: {"industries": ["<a name from the list>"]}"""


def ai_pick(theme: str, known: dict[str, str], ask) -> list[str]:
    """The industries the AI picks for a theme, only names on the market's list (anything else is dropped)."""
    got = ask(PICK_SYSTEM, f"THEME: {theme}\nLIST:\n" + json.dumps(sorted(known.values()), ensure_ascii=False))
    out = []
    for x in (got.get("industries") if isinstance(got, dict) else None) or []:
        n = known.get(key(x))
        if n and n not in out:
            out.append(n)
    return out[:6]


def _slug(theme: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(theme or "").lower()).strip("-")[:60]


# words every industry or theme shares, which say nothing about which industry: never matched on their own
_PLAIN = {"and", "the", "for", "with", "other", "others", "service", "services", "product", "products", "diversified", "industries", "industry",
          "misc", "miscellaneous", "general", "goods", "related", "allied", "india", "indian", "usa", "american", "stock", "stocks", "company",
          "companies", "sector", "sectors", "theme", "themes", "supply", "chain", "nec", "except", "including", "equipment", "equipments",
          "trading", "wholesale", "new", "based", "listed", "business", "businesses", "ltd", "inc"}


def _stem(w: str) -> str:
    """A word's start as industry names are matched on: plural and British/American endings aside ("fertilisers" and "Fertilizers",
    "ports" and "Port", "centres" and "Center" all meet on their first five letters)."""
    w = w.lower()
    if w.endswith("s") and len(w) > 4:
        w = w[:-1]
    return w[:5]


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) >= 3 and w not in _PLAIN}


def words_pick(theme: str, known: dict[str, str]) -> list[str]:
    """The official industries whose names share a word with the theme ("paints" -> Paints; "cloud software" -> the software industries):
    the rule a typed theme falls back on when the AI picks none or can't answer. Deterministic, both markets."""
    tw = _stems(theme)
    return [name for k, name in sorted(known.items()) if tw & _stems(k)] if tw else []


# a theme that names a subset (R18, the owner: "Private banks" pulled in the public-sector banks): the words people write for one, as the
# exchange's industry names spell it
_ALIAS = {"psu": "public", "government": "public", "pvt": "private", "listed": ""}


def _concept_stems(theme: str) -> set[str]:
    """The stems of the curated entries' own trigger words and phrases that this theme names (they say which theme, not which part of it)."""
    out = set()
    for c in concepts_of(theme):
        out |= _stems(" ".join(c["words"]) + " " + " ".join(c.get("phrases", ())))
    return out


def subset_pick(theme: str, industries: list[str]) -> tuple[list[str], list[str]]:
    """(the industries kept, the industries left out) when the theme's name narrows its curated industries: a word of the theme that is not
    the entry's own trigger ("private" in "Private banks", "components" in "Auto components") and that some of the industries' names carry
    keeps only those. A theme that names no such word keeps them all."""
    t = " ".join(_ALIAS.get(w, w) for w in re.findall(r"[a-z0-9]+", str(theme or "").lower()))
    want = _stems(t) - _concept_stems(theme) - {_stem(w) for w in SIZE_WORDS}
    if not want or len(industries) < 2:
        return list(industries), []
    keep = [i for i in industries if want & _stems(i)]
    if not keep or len(keep) == len(industries):
        return list(industries), []
    return keep, [i for i in industries if i not in keep]


# a theme of one size of company (the owner: "small-cap"): India by SEBI's ranks of market value (the largest 100 large, the next 150 mid,
# the rest small), the US by market value ($10 bn and up large, $2 bn to $10 bn mid, below small)
SIZE_WORDS = ("cap", "caps", "smallcap", "smallcaps", "midcap", "midcaps", "largecap", "largecaps")
IN_RANKS = {"large": (1, 100), "mid": (101, 250), "small": (251, 10 ** 9)}
US_BANDS = {"large": (10000.0, 1e18), "mid": (2000.0, 10000.0), "small": (0.0, 2000.0)}       # $ million


def size_band(theme: str) -> str | None:
    """"small", "mid" or "large" when the theme names a size of company ("Small-cap pharma", "midcap IT"), else None."""
    t = " ".join(re.findall(r"[a-z0-9]+", str(theme or "").lower()))
    m = re.search(r"\b(small|mid|large)\s?caps?\b", t)
    return m.group(1) if m else None


def in_band(region: str, band: str | None, rows: list[dict]) -> set[str] | None:
    """The symbols of the market's companies of that size (None: no size named, everyone is in)."""
    if not band:
        return None
    caps = sorted(((r.get("market_cap") or 0, r["symbol"]) for r in rows or [] if r.get("symbol") and r.get("market_cap")), key=lambda x: (-x[0], x[1]))
    if region == "US":
        lo, hi = US_BANDS[band]
        return {s for c, s in caps if lo <= c < hi}
    lo, hi = IN_RANKS[band]
    return {s for k, (_, s) in enumerate(caps, 1) if lo <= k <= hi}


def industries_for(region: str, theme: str, rows: list[dict], ask, get_setting, set_setting, now=None, held=None) -> dict:
    """{"industries", "how", "named", "except"}: the official industries at the theme's core. "how":
    - "list": the curated table (with its named members and exclusions);
    - "ai": the AI's pick from the market's official list, kept INDUSTRIES_DAYS;
    - "words": the industries whose names share a word with the theme, when the AI picks none or can't answer now (THEMES, 4 Nov: a
      typed theme never rests on the AI alone), or the theme is an industry's own name;
    - "pending": the AI couldn't answer and no industry shares a word (asked again on the next request); "none": no index yet.
    A theme that is an official industry's own name always has that industry. `ask(system, text)` is the AI's JSON answer.
    cl48 (R47, the live Release 46 Consumer retail deck: the pick asked again swapped "Family Clothing Stores", whose eight chains were all in
    an informative layer, for "Retail Stores, Nec"): when the pick is made again, an industry of the pick it replaces that the new one
    leaves out stays in it when `held(industries)` names it (theme_routes.held_industries: most of its companies were in an informative
    layer of the theme's previous live placement), so a new pick never drops companies the evidence had placed."""
    known = known_industries(rows)
    if not known:
        return {"industries": [], "how": "none", "named": [], "except": []}
    exact = known.get(key(theme))
    cur = curated(region, theme, known)
    if cur is not None:
        named, out = named_lists(region, theme)
        listed = {r.get("symbol") for r in rows or []}
        cur, drop = subset_pick(theme, cur + ([exact] if exact and exact not in cur else []))
        return {"industries": cur, "how": "list", "named": [s for s in named if s in listed], "except": out, "drop": drop}
    if exact:
        return {"industries": [exact], "how": "words", "named": [], "except": []}

    def answer(picked, how):
        if picked:
            return {"industries": picked, "how": how, "named": [], "except": []}
        words = words_pick(theme, known)
        return {"industries": words, "how": "words" if words else ("pending" if how == "pending" else how), "named": [], "except": []}
    now = now or datetime.now(timezone.utc)
    skey = f"theme:industries:{region}:{_slug(theme)}"
    try:
        hit = json.loads(get_setting(skey) or "null")
    except Exception:
        hit = None
    # cv47 (R46, the live Release 46 Consumer retail deck: the bump to RULES 45 asked the pick again and the AI swapped "Family Clothing
    # Stores", whose chains all sat in a layer, for "Retail Stores, Nec", whose companies fit none): a pick kept under PICK_RULES or later
    # rules is kept (INDUSTRIES_DAYS), so a change of the placement rules never redraws a theme's universe; one kept under older rules is
    # made again
    rules = hit.get("rules") if isinstance(hit, dict) else None
    if isinstance(hit, dict) and hit.get("at") and isinstance(rules, int) and PICK_RULES <= rules <= RULES:
        try:
            fresh = (now - datetime.fromisoformat(hit["at"])).days < INDUSTRIES_DAYS
        except ValueError:
            fresh = False
        if fresh:
            return answer([known[key(i)] for i in hit.get("industries") or [] if key(i) in known], "ai")
    try:
        picked = ai_pick(theme, known, ask)
    except Exception as e:                      # the AI busy: the words rule for now, the AI asked again next time
        print("theme base: industries not picked:", theme[:40], type(e).__name__, str(e)[:100])
        return answer([], "pending")
    kept_ = []
    was = [known[key(i)] for i in (hit.get("industries") or [] if isinstance(hit, dict) else []) if key(i) in known]
    dropped = [i for i in was if key(i) not in {key(x) for x in picked}]
    if picked and dropped and held is not None:
        try:
            kept_ = [i for i in held(dropped) or [] if i in dropped]
        except Exception as e:                  # the previous placement can't be read now: the new pick as it is
            print("theme base: industries of the previous pick not checked:", theme[:40], type(e).__name__, str(e)[:100])
        picked = picked + kept_
    try:
        set_setting(skey, json.dumps({"at": now.isoformat(timespec="seconds"), "industries": picked, "rules": RULES,
                                      **({"held": kept_} if kept_ else {})}, ensure_ascii=False))
    except Exception as e:
        print("theme base: industries not kept:", str(e)[:100])
    return answer(picked, "ai")


# ---------- membership ----------
def _named(m: dict) -> set[str]:
    return {c.get("ticker") for g in (m.get("value_chain") or []) + (m.get("sub_themes") or []) for c in g.get("companies") or [] if c.get("ticker")}


def with_base(m_before: dict, out: dict, rows: list[dict], industries: list[str], name_of=lambda n, s: n or s, named=(), exclude=(),
              drop=(), sized: set[str] | None = None) -> dict:
    """The checked map (`out`, from theme_check.check_placements on `m_before`) with every company of the theme's industries in it. Each
    company carries `base` (it is in an official industry of the theme), its `industry` and `cap` (the index's market value). A base company
    the AI put in a layer stays there when its words show it or weren't checked yet; one the check moved out of every layer, or the AI never
    named, is listed under its own industry as a layer of its own ("official": true), largest first. `placements` gets the honest counts:
    `total`, `base`, `added` (companies from other industries the AI named that are kept), `confirmed` (of those, shown in their own words),
    `left_out` (named additions whose own words said no) and the `industries`. `named`: the curated table's own members of the theme, base too
    (`basis` "list", listed under "Named in the theme's list" when the AI didn't place them); `exclude`: companies of the industries that are
    another theme's (solar-cell makers filed as semiconductors), out of the base unless the AI names them. `drop`: the industries a theme's
    name leaves out (subset_pick: the public-sector banks of "Private banks") and `sized`: the companies of the size it names (in_band), so
    a company the AI names from them is out too (R18)."""
    # a layer the AI left without a name (R20: four of the live Cybersecurity map's five, kept in the store from before ai.layer_name) is
    # dropped here too, so a stored map never draws "Layer 2 ·": its companies are then placed as any company the AI didn't name
    # R25: and one whose name only stands in for one ("placeholder" in the live R24 Insurance map), kept in the store from before ai.stand_in
    from .ai import stand_in
    m_before = {**m_before, "value_chain": [v for v in m_before.get("value_chain") or [] if v.get("official") or not stand_in(v.get("layer"))]}
    out = {**out, "value_chain": [v for v in out.get("value_chain") or [] if v.get("official") or not stand_in(v.get("layer"))]}
    idx = {r["symbol"]: r for r in rows or [] if r.get("symbol")}
    inset = {key(i) for i in industries}
    skip = set(exclude)
    gone = {key(i) for i in drop}
    by_industry = {s: r for s, r in idx.items() if key(r.get("industry")) in inset and s not in skip and (sized is None or s in sized)}
    by_list = {s: idx[s] for s in named if s in idx and s not in by_industry and (sized is None or s in sized)}
    base = {**by_industry, **by_list}

    def outside(c) -> bool:              # a company the theme's own name leaves out, whoever named it
        sym = c.get("ticker")
        if sym in base:
            return False
        r = idx.get(sym) or {}
        return key(r.get("industry")) in gone or (sized is not None and sym in idx and sym not in sized)
    # t56: each company the theme's own name leaves out, said as a business-membership decision of the theme's scope (its removal's reason)
    scoped = {}
    for g in (out.get("value_chain") or []) + (out.get("sub_themes") or []):
        for c in g.get("companies") or []:
            if c.get("ticker") and outside(c):
                r = idx.get(c["ticker"]) or {}
                scoped.setdefault(c["ticker"], {"ticker": c["ticker"], "name": c.get("name") or c["ticker"], "said": "scope",
                                                "scope": "of an industry the theme's name leaves out" if key(r.get("industry")) in gone
                                                else "outside the size the theme's name states"})
    out = {**out, "value_chain": [{**v, "companies": [c for c in v.get("companies") or [] if not outside(c)]} for v in out.get("value_chain") or []],
           "sub_themes": [{**x, "companies": [c for c in x.get("companies") or [] if not outside(c)]} for x in out.get("sub_themes") or []]}
    out["value_chain"] = keep_map_layers(m_before, out["value_chain"], base)

    def tag(c):
        r = idx.get(c.get("ticker")) or {}
        sym = c.get("ticker")
        return {**c, "base": sym in base, "basis": "industry" if sym in by_industry else "list" if sym in by_list else "added",
                "industry": r.get("industry") or "", "cap": r.get("market_cap")}
    out = dict(out)
    out["value_chain"] = [{**v, "companies": [tag(c) for c in v.get("companies") or []]} for v in out.get("value_chain") or []]
    out["sub_themes"] = [{**s, "companies": [tag(c) for c in s.get("companies") or []]} for s in out.get("sub_themes") or []]
    in_layer = {c["ticker"] for v in out["value_chain"] for c in v["companies"]}
    groups = [(ind, "industry", [r for s, r in by_industry.items() if key(r.get("industry")) == key(ind)]) for ind in industries]
    groups.append(("Named in the theme's list", "list", list(by_list.values())))
    for name, basis, members in groups:
        cos = sorted((r for r in members if r["symbol"] not in in_layer), key=lambda r: (-(r.get("market_cap") or 0), r["symbol"]))
        if cos:
            out["value_chain"].append({"layer": plain_industry(name) if basis == "industry" else name, "description": "", "official": True, "basis": basis,
                                       "companies": [{"ticker": r["symbol"], "name": name_of(r.get("name"), r["symbol"]), "what": "", "verified": False,
                                                      "base": True, "basis": basis, "industry": r.get("industry") or "", "cap": r.get("market_cap")} for r in cos]})
    placed = _named(out)
    added = {c["ticker"]: c for g in out["value_chain"] + out["sub_themes"] for c in g["companies"] if not c["base"]}
    confirmed = {s for s in added if any(c["ticker"] == s and c.get("verified") for g in out["value_chain"] + out["sub_themes"] for c in g["companies"])}
    out["screen"] = [x for x in out.get("screen") or [] if x.get("ticker") in placed]
    out["placements"] = {**(out.get("placements") or {}), "placed": len(placed), "total": len(placed), "base": len(base), "named": len(by_list),
                         "added": len(added), "confirmed": len(confirmed), "unconfirmed": len(added) - len(confirmed),
                         "left_out": len({s for s in _named(m_before) if s not in placed and s not in base}), "industries": list(industries)}
    if scoped:
        out["placements"]["dropped"] = list(out["placements"].get("dropped") or []) + [x for s, x in scoped.items() if s not in placed]
    return out


CONFIRMED_SAID = "its own words were checked to show"        # t56: how a stored version says a member's words were checked (theme_data)


def keep_confirmed(out: dict, m: dict, confirmed: dict) -> dict:
    """t56 (R55 review: "if the map re-ask is unstable, keep a previously confirmed member unless evidence removes it"; the live R55 Payments
    map dropped Adyen, which R54 had added): the checked map (theme_check.check_placements) with each company the check left out of every
    group the map named it in only on a "yes" its words didn't back ("dropped", "said": "unbacked"), and that the previous published version
    of the same map had as a member (`confirmed`: {symbol: "confirmed" when its own words were checked to show the theme's work there, else
    "member"}), back in those groups, not confirmed this time ("verified" False) and saying why ("kept_member"): an unbacked "yes" is no
    evidence against it. A clear "no" of its own words still leaves it out (evidence removes it), its reason kept in "dropped"."""
    pl = dict(out.get("placements") or {})
    dropped = [x for x in pl.get("dropped") or [] if isinstance(x, dict)]
    back = [x for x in dropped if x.get("said") == "unbacked" and x.get("ticker") in (confirmed or {})]
    if not back:
        return out
    syms = {x["ticker"] for x in back}
    said = lambda s_: ("the version before had its own words checked to show the theme's work" if confirmed.get(s_) == "confirmed"      # noqa: E731
                       else "the version before had it as a member") + \
        "; this check said it does the work but its words didn't back the answer, which removes nothing: kept, not confirmed this time"
    out = dict(out)
    for k in ("value_chain", "sub_themes"):
        was, now = list(m.get(k) or []), list(out.get(k) or [])
        for i, g in enumerate(was[:len(now)]):
            have = {c.get("ticker") for c in now[i].get("companies") or []}
            add = [{**c, "what": "", "verified": False, "kept_member": said(c["ticker"])} for c in g.get("companies") or [] if c.get("ticker") in syms
                   and c.get("ticker") not in have]
            if add:
                now[i] = {**now[i], "companies": list(now[i].get("companies") or []) + add}
        out[k] = now
    pl["dropped"] = [x for x in dropped if x.get("ticker") not in syms]
    if not pl["dropped"]:
        pl.pop("dropped")
    pl["kept_members"] = [{"ticker": x["ticker"], "name": x.get("name") or x["ticker"], "why": said(x["ticker"])} for x in back]
    pl["left_out"] = max(0, int(pl.get("left_out") or 0) - sum(len(x.get("groups") or [1]) for x in back))
    pl["placed"] = int(pl.get("placed") or 0) + len(back)
    pl["unconfirmed"] = int(pl.get("unconfirmed") or 0) + len(back)
    out["placements"] = pl
    return out


def keep_map_layers(m_before: dict, layers: list[dict], base: dict) -> list[dict]:
    """The AI map's own layers kept as the theme's scheme (R20: "Private banks" lost "Deposit gathering", "Retail and SME lending"... when
    the check of each bank's own words against each layer said no for nearly all of them, and every bank fell back to its exchange industry,
    one layer). When the check leaves fewer than two of the map's layers with a company but the map placed companies of the theme's own
    industries in two or more, each such company goes back to the first of the map's layers that named it ("verified" False: placed by the
    map, its words not checked for that layer). A company from another industry the check said no to stays out."""
    own = [v for v in layers if not v.get("official") and v.get("companies")]
    if len(own) >= 2:
        return layers
    before = {v.get("layer"): [c for c in v.get("companies") or [] if c.get("ticker") in base] for v in m_before.get("value_chain") or [] if not v.get("official")}
    if sum(1 for cos in before.values() if cos) < 2:
        return layers
    seen = {c.get("ticker") for v in layers for c in v.get("companies") or []}
    out = []
    for v in layers:
        add = []
        if not v.get("official"):
            for c in before.get(v.get("layer")) or []:
                if c.get("ticker") not in seen:
                    seen.add(c.get("ticker"))
                    add.append({**c, "what": "", "verified": False, "by_map": True})
        out.append({**v, "companies": list(v.get("companies") or []) + add} if add else v)
    return out


# ---------- every company in one of the map's layers (R21) ----------
# The AI's map names a few companies a layer (Defence: 12 of 42 in its five layers; IT services: one layer of its own beside three of the
# exchange's industries). After the map, the companies of the theme's industries it didn't place are put in the best of its own layers from
# their own words: one batched AI answer a theme (kept with the map), else by the words they share with each layer's name and description.
# Only a company that fits no layer goes to one "Other <theme> companies" layer; the exchange's industries are never layers beside the map's.
PLACE_MAX = 120                  # companies one AI answer places (the largest first); the rest by their words


def _place_words(layers: list[dict], what: str, industry: str) -> str:
    """The map layer whose name and description share the most words with a company's own words (and its industry's name), or "" for none."""
    from .theme_data import _stems, does_the_work
    # e81 (LIVE17A-004: Medalist Diversified, a retail, flex and hotel owner, placed by its words in "Towers, data centres and niche property",
    # whose long description shares more of any landlord's words than a short name does): a company whose words say a word only one layer's
    # name says ("retail", "office", "healthcare") is placed in the layer whose name it says, the description's words only between those
    names_ = {v.get("layer") or "": _stems(v.get("layer") or "") for v in layers}
    mine_ = _stems(what or "")
    own_hits = {}
    for nm, ws in names_.items():
        only = ws - set().union(*(x for k, x in names_.items() if k != nm)) if len(names_) > 1 else ws
        k_ = sum(1 for m_ in mine_ if any(m_ == w or (len(w) >= 5 and (m_.startswith(w) or w.startswith(m_))) for w in only))
        if k_:
            own_hits[nm] = k_
    if own_hits:
        layers = [v for v in layers if (v.get("layer") or "") in own_hits]
    best, score = "", 0
    for v in layers:
        words = _stems(f"{v.get('layer') or ''} {v.get('description') or ''}")
        mine = _stems(what or industry)          # its own words; the industry's name only when it has none (every company shares it)
        k = sum(1 for m_ in mine if any(m_ == w or (len(w) >= 5 and (m_.startswith(w) or w.startswith(m_))) for w in words))
        if k > score or (k == score and k and does_the_work(what, _stems(v.get("layer") or ""))):
            best, score = v.get("layer") or "", k
    return best if score else ""


RESIDUAL_SHARE, RESIDUAL_MIN = 0.15, 5      # an "Other" layer this large (a share of the companies, or a count) gets extra layers proposed


def other_label(theme: str) -> str:
    """"Other <theme> companies" with the theme's last word singular, as an adjective reads (R22: "Other semiconductors companies")."""
    words = " ".join(str(theme or "the theme").split()).split(" ")
    last = words[-1]
    if last.lower().endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif last.lower().endswith("s") and not last.lower().endswith(("ss", "us", "is")) and len(last) > 3 and not last.isupper():
        last = last[:-1]
    words[-1] = last
    label = " ".join(words)
    if label[:1].isupper() and not label[:2].isupper():
        label = label[:1].lower() + label[1:]
    return f"Other {label} companies"


def sub_theme_only(m: dict) -> list[dict]:
    """The companies the map names in a sub-theme only, in no layer of its value chain, each once (d1: the live Release 41 decks listed SAIL,
    GAIL, MercadoLibre, O'Reilly and Etsy in no layer and not in "Other" either)."""
    in_vc = {c.get("ticker") for v in m.get("value_chain") or [] for c in v.get("companies") or []}
    out: dict = {}
    for sub in m.get("sub_themes") or []:
        for c in sub.get("companies") or []:
            if c.get("ticker") and c["ticker"] not in in_vc:
                out.setdefault(c["ticker"], c)
    return list(out.values())


def with_sub_only(m: dict, theme: str) -> dict:
    """The map with each company it names in a sub-theme only (sub_theme_only) in its "Other" group (made when it has none), so every company
    of the theme is in a layer or in "Other", never in neither (d1). A map whose own layers place them (place_rest) has none left."""
    only = sub_theme_only(m)
    if not only:
        return m
    vc = [dict(v, companies=list(v.get("companies") or [])) for v in m.get("value_chain") or []]
    rest = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    if rest is None:
        rest = {"layer": other_label(theme or m.get("sector") or ""), "description": "", "official": True, "basis": "rest", "companies": [],
                "sub_only": True}
        vc.append(rest)
    rest["companies"] = sorted(rest["companies"] + [{**c, "sub_only": True} for c in only], key=lambda c: (-(c.get("cap") or 0), c.get("ticker") or ""))
    return {**m, "value_chain": vc}


def with_earlier(answer: dict, earlier: dict) -> dict:
    """rv51 (R51, the live Release 49 IT services placement: 139 of 252 companies in informative layers became 132, as an answer asked for two
    new companies dropped the kept answer's two extra layers): a placement answer with an earlier one's layer names and extra layers kept:
    each name the earlier answer gave a layer, and each extra layer it proposed (by name), stays; the newer answer adds those it lacks, and
    the companies it alone placed. Nothing else of the newer answer changes."""
    earlier = earlier if isinstance(earlier, dict) else {}
    out = dict(answer or {})
    out["rename"] = {**(out.get("rename") or {}), **(earlier.get("rename") or {})}
    held = list(earlier.get("extra") or [])
    known = {str(x.get("name") or "").strip().lower() for x in held if isinstance(x, dict)}
    out["extra"] = held + [x for x in out.get("extra") or [] if isinstance(x, dict) and str(x.get("name") or "").strip().lower() not in known]
    if isinstance(earlier.get("assign"), dict) and isinstance(out.get("assign"), dict):
        out["assign"] = {**earlier["assign"], **out["assign"]}
    return out


def fill_earlier(answer: dict, earlier: dict) -> dict:
    """gl52 (R52): a placement answer with an older one's layer names and extra layers added only where it has none of its own: a layer it
    names keeps its name, an extra layer it proposes (by name) is not doubled; the older answer's companies are taken only where it placed
    none. Nothing it holds changes."""
    earlier = earlier if isinstance(earlier, dict) else {}
    out = dict(answer or {})
    out["rename"] = {**(earlier.get("rename") or {}), **(out.get("rename") or {})}
    have = list(out.get("extra") or [])
    known = {str(x.get("name") or "").strip().lower() for x in have if isinstance(x, dict)}
    out["extra"] = have + [x for x in earlier.get("extra") or [] if isinstance(x, dict) and str(x.get("name") or "").strip().lower() not in known]
    if isinstance(earlier.get("assign"), dict) and isinstance(out.get("assign"), dict):
        out["assign"] = {**earlier["assign"], **out["assign"]}
    return out


def place_rest(m: dict, theme: str, about_of, ask=None, kept: dict | None = None, facts_of=None, carried: bool = False,
               previous: dict | None = None, off_before: dict | None = None, moved_before: dict | None = None, moved_out: dict | None = None,
               figures_of=None, published: dict | None = None) -> tuple[dict, dict]:
    """(the map with every base company in one of the map's own layers, the answer as worked out: {"assign": {symbol: {"layer", "by"}},
    "rename": {layer: {"name", "description"}}, "extra": [{"name", "description", "symbols"}]}). Runs only when the map has layers of its own;
    companies in its official-industry or named-list layers (not a list grouped by industry) are placed: from `kept` (the answer kept with the map),
    else one `ask` answer for up to PLACE_MAX of them, which also renames a layer whose name doesn't fit the companies it then holds and proposes
    up to two more layers when many fit none (R22); else by their words, the map's names kept. A company placed this way is marked "placed" (its
    words weren't checked against that layer, so it isn't "verified"); one that fits none goes to one "Other <theme> companies" layer.
    R25: the same answer gives each company's revenue model ("models": {symbol: model}, kept with the rest, so asked once a map); the layers are
    then split so each holds one way of earning (by_model).
    R26: each company's model rests on more of what the app keeps (`facts_of(symbol)` -> {"industry": its official industry path, "segments":
    [names], "filings": its filings' titles}, stored only), is kept only when that evidence shows it (theme_check.model_supported; else asked
    once more with the evidence, else unknown), and a layer the split reshaped whose name no longer fits how its companies earn is renamed
    (theme_check.names_for_models): every answer kept with the map, so asked once.
    R27: the same answer gives each company's secondary ways of earning ("model_tags") and how directly its evidence states its model
    ("model_confidence": high, medium, low; theme_check.model_confidence), kept with the rest; a company the AI left unknown whose own words
    state a model in so many words gets it ("medium"); the evidence also carries the company page's stored business read (`facts_of` ->
    "business") and the sentences of its description that speak of how it earns.
    R41 (lane s2-exact, the live Release 38.1 Pharma deck: Hikal and Brooks left the contract research layer the answer placed them in when
    the bump to RULES 40 asked their unknown models again): `carried`, a kept answer kept under an earlier rules version (theme_routes.placed),
    sticks: no unknown model is asked again (reask_unknown), a names check asked again changes no model or layer name the answer holds (it
    only adds those it lacks), and a layer the split renamed keeps the answer's name when the split reshapes it again (only a reshaped layer
    the answer never named is asked). Whatever the version, a model asked apart from the placement (R30, kept in "reasked") never moves the
    company out of the map layer the placement put it in (by_model `settled`).
    R45 (lane tx2, the outside review of the live Release 45 Automotive deck: Bosch and Asahi India Glass left the component suppliers'
    layer they were in on the live Release 43): `previous`, {symbol: its layer in the previous live placement as shown} (theme_changes'
    snapshot, theme_routes.placed): a company the split would move out of the layer it was in there moves only on evidence of the new
    layer (by_model `previous`), and an unchecked map pick keeps it without evidence of the layer it is in (held_to_previous).
    d53 (R53): `off_before`, the companies an earlier stored version dropped as another business (theme_changes.off_memory): each stays out
    while no words of its own are read (without_off_industry); one its words now keep in is named in the placements' "back" with why.
    c54 (R53 review): `moved_before`, {symbol: [from, to]} of the moves the stored change log records (theme_changes.move_memory): a company
    new to a layer named by what it sells (`previous` another layer, or a logged move into it) joins it only on evidence it sells that
    (by_model sold_what); a named layer of the previous version a re-check would lose comes back with its companies that still fit
    (restore_vanished), each lost layer listed in the placements' "layers_gone".
    v55 (R55): a company is displayed in the map's layer of its own stage (stage_moves: commercial or development, by its own words, else its
    stored revenue, `figures_of(symbol)` -> {"revenue", "ebitda"}); a company whose principal business the theme's definition doesn't include
    is screened out before any layer (without_off_industry `scope`); a contract manufacturer or component supplier of the theme's products
    left in "Other" goes to a layer of that kind, or is said to be one there (fallback_layer).
    p57 (R56 review): the placement contract as the last steps, whatever rule moved a company: a layer a rule made whose name its members'
    own words contradict is named by what they say or not made, and no new one-company layer is made by a rule (truthful_layers); then each
    published member (`published`: {symbol: its published layer}, theme_changes.published_members, every member of the stored version and
    each a re-check removed on a check's answer alone) a rule moved without printed evidence is back in its published layer (hold_published).
    Said in the placements' "contract"."""
    from .theme_check import (MODEL_MEMBERS, earning_lines, model_confidence, model_evidence, model_supported, model_tags, refine_model,
                              names_for_models, recheck_models, stated_model)
    vc = list(m.get("value_chain") or [])
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    rest = [v for v in vc if v.get("official") and v.get("basis") in ("industry", "list") and not v.get("by_industry")]
    todo = [c for v in rest for c in v.get("companies") or []]
    kept = kept if isinstance(kept, dict) and "assign" in kept else {}
    if not own:
        return m, kept
    # d1 (the live Release 41 decks: SAIL, GAIL, MercadoLibre, O'Reilly and Etsy, named by the AI in a sub-theme only, were in no layer and not
    # in "Other"): a company the map names in a sub-theme only is placed like one of the theme's industries: in the map layer the answer or
    # its own words give it, else in "Other"
    todo += sub_theme_only(m)
    names = {v["layer"] for v in own}
    got = {s: x for s, x in (kept.get("assign") or {}).items() if isinstance(x, dict) and (x.get("layer") in names or x.get("layer") == "")}
    rename, extra = dict(kept.get("rename") or {}), list(kept.get("extra") or [])
    need = [c for c in sorted(todo, key=lambda c: -(c.get("cap") or 0)) if c["ticker"] not in got]
    asked, placed_models, placed_tags, placed_conf = False, None, {}, {}
    by_sym = {c.get("ticker"): c for v in vc for c in v.get("companies") or [] if c.get("ticker")}
    by_sym.update({c["ticker"]: c for c in todo if c.get("ticker") and c["ticker"] not in by_sym})
    facts: dict[str, dict] = {}

    def facts_for(sym) -> dict:
        if sym not in facts:
            f = {}
            if facts_of is not None:
                try:
                    f = facts_of(sym) or {}
                except Exception as e:           # a store that can't answer now: the company's own words and industry still count
                    print("theme base: company facts not read:", sym, type(e).__name__, str(e)[:100])
            facts[sym] = f if isinstance(f, dict) else {}
        return facts[sym]

    def evidence(sym, words: bool = True) -> str:
        """A company's evidence of how it earns (theme_check.model_evidence); `words` False leaves out its description (sent beside it)."""
        c, f = by_sym.get(sym) or {}, facts_for(sym)
        own_words = about_of(sym) or c.get("what") or ""
        about = own_words if words else ""
        earns = None
        if not words:        # sent beside its description (its first 220 characters, or its one line): only what those leave out
            earns = earning_lines(own_words, limit=240)
            earns = "" if earns[:60] in str(own_words)[:200] else earns
        return model_evidence(f.get("industry") or c.get("industry") or "", about, f.get("segments") or (), f.get("filings") or "",
                              business=f.get("business") or "", earns=earns)

    def checked_models(ans: dict, syms) -> tuple[dict, dict, dict]:
        """(models, tags, confidence): the models the AI gave, each kept only when the company's evidence shows it; the rest asked once more
        with it, else unknown; one of `syms` still unknown whose own words state a model in so many words gets that one (R27, "medium").
        Each kept model's confidence is how directly its evidence states it (at most "medium" for one asked again), its tags those its
        evidence shows."""
        keep, rejected, tags, conf = {}, [], {}, {}
        for s_, md in (ans.get("models") or {}).items():
            ev = evidence(s_)
            if model_supported(md, ev):
                keep[s_] = md
                conf[s_] = model_confidence(md, ev, (ans.get("confidence") or {}).get(s_, ""))
                t = model_tags((ans.get("tags") or {}).get(s_), md, ev)
                if t:
                    tags[s_] = t
            else:
                rejected.append({"symbol": s_, "name": (by_sym.get(s_) or {}).get("name") or s_, "was": md, "evidence": ev})
        if rejected and ask is not None:
            try:
                for s_, md in recheck_models(rejected, ask, theme).items():
                    keep[s_] = md
                    conf[s_] = model_confidence(md, evidence(s_), "medium")
            except Exception as e:           # the AI busy: those companies' models stay unknown
                print("theme base: models not asked again:", theme[:40], type(e).__name__, str(e)[:100])
        for s_ in dict.fromkeys(syms if ans.get("models") else ()):     # R30: an answer that gave no models is left as it came
            if s_ and s_ not in keep:
                ev = evidence(s_)
                md = stated_model(ev)             # R37: each family's words, making and trading words too
                if md and model_supported(md, ev):
                    keep[s_], conf[s_] = md, "medium"
        # R29: a broad model (utility, resources, a maker in a metals industry) made exact where the evidence shows one kind only, so
        # regulated networks, generators and traders, or miners and fabricators, are never one layer
        for s_, md in list(keep.items()):
            keep[s_] = refine_model(md, evidence(s_))
            if keep[s_] != md:
                conf[s_] = model_confidence(keep[s_], evidence(s_), said_for(keep[s_], md, conf.get(s_, "")))
        return keep, tags, conf
    if need and ask is not None:
        asked = True
        from .theme_check import place_in_layers
        try:
            with_ev = [{**v, "companies": [{**c, "evidence": evidence(c.get("ticker"), not c.get("what"))} for c in (v.get("companies") or [])[:MODEL_MEMBERS]]}
                       for v in own]
            ans = place_in_layers(with_ev, [{"symbol": c["ticker"], "name": c.get("name") or c["ticker"], "industry": c.get("industry") or "",
                                         "about": about_of(c["ticker"]) or "", "evidence": evidence(c["ticker"], False)} for c in need[:PLACE_MAX]],
                                  ask, theme)
            got.update({s: {"layer": x if x in names else "", "by": "ai"} for s, x in ans["place"].items()})
            # rv51 (R51, the live Release 49 IT services placement: an answer asked for 2 companies the kept answer lacked replaced its
            # renames and its two extra layers, and the 17 companies those layers held went to "Other" or other layers): an answer for the
            # companies a kept answer didn't place only adds names and extra layers; those the kept answer holds stick (with_earlier)
            fresh = {"rename": {k: v for k, v in ans["rename"].items() if k in names}, "extra": ans["extra"]}
            both = with_earlier(fresh, {"rename": rename, "extra": extra}) if kept else fresh
            rename, extra = both["rename"], both["extra"]
            placed_models, placed_tags, placed_conf = checked_models(ans, [c["ticker"] for c in need[:PLACE_MAX]]
                                                                     + [c.get("ticker") for v in with_ev for c in v["companies"]])
        except Exception as e:               # the AI busy: the words place them now, the AI is asked again on the next check
            print("theme base: companies not placed by the AI:", theme[:40], type(e).__name__, str(e)[:100])
    for c in need:
        if c["ticker"] not in got:
            got[c["ticker"]] = {"layer": _place_words(own, about_of(c["ticker"]) or c.get("what") or "", plain_industry(c.get("industry"))), "by": "words"}
    by_layer: dict[str, list] = {}
    other = []
    for c in todo:
        x = got.get(c["ticker"]) or {}
        # d1: one placed in no layer with no words of its own (no description kept, no line from the map), by the AI's answer on its name or
        # by its words: not checked yet, never "fits none of the layers"
        unread = not x.get("layer") and not (about_of(c["ticker"]) or c.get("what"))
        tag = {**c, "placed": x.get("by") or "words", "verified": c.get("verified", False) if c.get("sub_only") or not c.get("base", True) else False,
               **({"fit": True} if x.get("layer") else {}), **({"unread": True} if unread else {})}
        (by_layer.setdefault(x["layer"], []) if x.get("layer") else other).append(tag)
    total = sum(len(v.get("companies") or []) for v in vc)
    extra_layers = []
    if extra and other and (len(other) >= RESIDUAL_MIN or len(other) > RESIDUAL_SHARE * max(1, total)):
        left = {c["ticker"]: c for c in other}
        for x in extra[:2]:
            cos = [{**left.pop(s_), "fit": True} for s_ in x.get("symbols") or [] if s_ in left]
            if len(cos) >= 2:
                extra_layers.append({"layer": x["name"], "description": x.get("description") or "", "by_place": True, "companies": cos})
        other = list(left.values())
    # the layers' names checked against the companies they hold once a map and its placements (R23: a map with nothing left to place kept
    # "Raw materials and castings" for forgers, since the check rode only on the placement call): asked again only when the members change
    sig = names_signature(own, by_layer)
    names_for = kept.get("names_for") if kept.get("names_for") == sig else None
    # how each company earns (R25): asked with the placements or the names' check, once a map; kept with them, never asked again for that map
    models = kept.get("models") if isinstance(kept.get("models"), dict) else None
    tags = dict(kept.get("model_tags") or {}) if isinstance(kept.get("model_tags"), dict) else {}
    conf = dict(kept.get("model_confidence")) if isinstance(kept.get("model_confidence"), dict) else None
    if asked:
        names_for = sig
        if placed_models is not None:
            models, tags, conf = {**(models or {}), **placed_models}, {**tags, **placed_tags}, {**(conf or {}), **placed_conf}
    elif ask is not None and (names_for is None or models is None):
        from .theme_check import place_in_layers
        try:
            said = lambda c: {**c, "what": c.get("what") or one_line(about_of(c.get("ticker")) or ""),           # noqa: E731 (its own words, for its model)
                              "evidence": evidence(c.get("ticker"), not c.get("what"))}
            sent = [{**v, "companies": [said(c) for c in (list(v.get("companies") or []) + by_layer.get(v["layer"], []))[:MODEL_MEMBERS]]} for v in own]
            raw: dict = {}
            ans = place_in_layers(sent, [], lambda s_, t_: raw.setdefault("r", ask(s_, t_)), theme)
            if not (isinstance(raw.get("r"), dict) and raw["r"]):
                # p57 (lane g57: with a model that answers nothing, the Payments placement moved Block, PayPal and Coinbase and lost a
                # layer): an empty answer is no answer: what the kept answer holds stays, asked again on a later check
                raise ValueError("the answer gave no names and no models")
            new_rename, names_for = {k: x for k, x in ans["rename"].items() if k in names}, sig
            new_models, new_tags, new_conf = checked_models(ans, [c.get("ticker") for v in sent for c in v["companies"]])
            if carried and models:         # R41: the carried answer's models and names stick; the check only adds what it lacks
                rename = {**new_rename, **{k: x for k, x in rename.items() if k in names}}
                tags = {**new_tags, **{s_: t for s_, t in tags.items() if s_ in models}}
                conf = {**(new_conf or {}), **(conf or {})}
                models = {**new_models, **models}
            else:
                rename, models, tags, conf = new_rename, new_models, new_tags, new_conf
        except Exception as e:
            print("theme base: layer names not checked:", theme[:40], type(e).__name__, str(e)[:100])
    reasked = list(kept.get("reasked") or []) if isinstance(kept.get("reasked"), list) else []
    retry = published is not None and kept.get("reasked_rules") != RULES
    if retry:
        # p57 (contract 1; x57: ADP, asked once under earlier rules, still with no model): a company that failed (its model still unknown)
        # is asked once more under each rules version, bounded as before (REASK_MAX a check); one with a model is never asked again
        reasked = [s_ for s_ in reasked if (models or {}).get(s_) not in (None, "", "unknown")]
    every_sym = [c.get("ticker") for c in todo] + [c.get("ticker") for v in own for c in v.get("companies") or []]
    # gl50: every company still without a model, the largest first, asked in batches on each check with the AI until each is asked once
    # (it ran only for a kept placement whose answer had models, never a carried one, 40 in one answer)
    if ask is not None and not asked:
        big = sorted(dict.fromkeys(x for x in every_sym if x), key=lambda x: (-((by_sym.get(x) or {}).get("cap") or 0), x))
        models, tags, conf, reasked = reask_unknown(models, tags, conf, reasked, big, about_of, by_sym, evidence, ask, theme)
        models = models or None

    out_vc = []
    for v in vc:
        if v in rest:
            continue
        if v in own:
            v = {**v, "companies": list(v.get("companies") or []) + by_layer.get(v.get("layer"), [])}
            r = rename.get(v["layer"])
            if r and r.get("name"):            # a name that fits the companies the layer now holds; the map's name kept as "was" (R22)
                v = {**v, "layer": r["name"], "description": r.get("description") or v.get("description") or "", "was": v["layer"],
                     "aka": list(dict.fromkeys((v.get("aka") or []) + [v["layer"]]))}          # d53: every name it had (theme_data.same_names)
        out_vc.append(v)
    out_vc += extra_layers
    if other:
        out_vc.append({"layer": other_label(theme), "description": "", "official": True, "basis": "rest",
                       "companies": sorted(other, key=lambda c: (-(c.get("cap") or 0), c["ticker"]))})
    model_names = None
    # gl50: with no model from any answer, the models the companies' own words state (R37's rule, which ran only beside answered models)
    # (the companies of the map's own layers only: they are for its figures, and move nobody out of "Other" or a layer: settled)
    models, conf, stated_ = stated_for_rest(models, conf, [c.get("ticker") for v in out_vc if not v.get("official") for c in v.get("companies") or []],
                                            evidence)
    if models:
        # R32: a company whose own stored words say nothing of how it earns takes the model its map layer's name states (live R31 semis:
        # Qualcomm, Broadcom, AMD... with only "From its own filings: Quarterly report" as evidence sat unknown in "Fabless chip design")
        models, conf = models_from_layer(out_vc, models, conf, evidence)
    settled = set()
    if models:
        # R31: a kept placement's models made exact by the R31 boundaries (lenders, landlords and developers; fabless and fab owners) from the
        # companies' evidence, with nothing asked again
        had = {s_ for s_, m_ in models.items() if m_ not in ("", "unknown")}
        models, conf = refine_kept(models, conf, evidence, [c.get("ticker") for v in out_vc for c in v.get("companies") or []])
        settled = {s_ for s_, m_ in models.items() if m_ not in ("", "unknown") and s_ not in had           # R37: models only their words state
                   and refine_model("unknown", evidence(s_)) in ("", "unknown")}
        # R41: a model asked apart from the placement (reask_unknown) moves no company out of the map layer the map itself or the AI's
        # placement answer put it in; one placed by its words alone, or in a layer the answer proposed for the companies that fit none of
        # the map's, moves as before
        settled |= {s_ for s_ in reasked if s_ not in got or (got[s_].get("by") == "ai" and got[s_].get("layer"))}
        settled |= stated_

    if previous:
        out_vc = held_to_previous(out_vc, map_names_of(previous, kept), about_of)
    out_vc = definition_fit(out_vc, evidence, theme, about_of)  # gl50: what the layer is, in the company's words or industry
    if models:
        before = {v["layer"]: {c.get("ticker") for c in v["companies"]} for v in out_vc if not v.get("official")}
        out_vc = by_model(out_vc, models, theme, tags=tags, confidence=conf, evidence_of=evidence, settled=settled,
                          previous=map_names_of(previous, kept), moved_before=moved_before, about_of=about_of, published=published)
        # R26: a layer of the map the split reshaped (companies moved in or out) whose name no longer fits how its companies earn is renamed by
        # the same check as the placement's; asked once a map and its split, kept with the rest
        reshaped = [v for v in out_vc if v["layer"] in before and not v.get("official") and not v.get("scale") and (v.get("model") or {}).get("line")
                    and not v["model"].get("sparse") and {c.get("ticker") for c in v["companies"]} != before[v["layer"]]]
        msig = model_names_signature(reshaped)
        model_names = kept.get("model_names") if isinstance(kept.get("model_names"), dict) and kept["model_names"].get("sig") == msig else None
        held_names = {}
        if model_names is None and carried and isinstance(kept.get("model_names"), dict):
            # R41: a carried answer's names for the layers the split renamed stick when the split reshapes them again
            held_names = {k: x for k, x in (kept["model_names"].get("rename") or {}).items() if k in {v["layer"] for v in reshaped}}
            if held_names and (ask is None or all(v["layer"] in held_names for v in reshaped)):
                model_names = {"sig": msig, "rename": held_names}
        if model_names is None and ask is not None and reshaped:
            try:
                ask_for = [v for v in reshaped if v["layer"] not in held_names]
                raw_n: dict = {}
                got_names = names_for_models(ask_for, lambda s_, t_: raw_n.setdefault("r", ask(s_, t_)), theme)
                if not got_names and ask_for and not (isinstance(raw_n.get("r"), dict) and raw_n["r"]):
                    # p57: an empty answer is no answer: the names the kept answer gave these layers stay (else none is renamed now)
                    raise ValueError("the names check gave no names")
                model_names = {"sig": msig, "rename": {**got_names, **held_names}}
            except Exception as e:
                print("theme base: layer names after the split not checked:", theme[:40], type(e).__name__, str(e)[:100])
        if model_names and model_names.get("rename"):
            out_vc = renamed_after_split(out_vc, {v["layer"] for v in reshaped}, model_names["rename"])
    out_vc = refits_kept(out_vc)
    # v55 (R55): a commercial-stage company never displayed in a layer named by a development stage, nor the other way round (stage_moves)
    words_of = lambda s_: about_of(s_) or (by_sym.get(s_) or {}).get("what") or ""          # noqa: E731
    figs: dict = {}

    def figures_for(sym) -> dict:
        if sym not in figs:
            try:
                figs[sym] = (figures_of(sym) if figures_of is not None else None) or {}
            except Exception as e:           # a store that can't answer now: its words still say its stage
                print("theme base: stored figures not read:", sym, type(e).__name__, str(e)[:100])
                figs[sym] = {}
        return figs[sym]
    out_vc, staged_n = stage_moves(out_vc, words_of, theme, figures_for)
    # gl52 (R52): a company left out for want of words whose description was looked for in every source and none found says so ("none_found",
    # theme_routes._facts_reader `searched`), never "not checked yet"
    out_vc = [{**v, "companies": [{**c, "out_why": "none_found"} if c.get("out_why") == "no_words" and facts_for(c.get("ticker")).get("searched") else c
                                  for c in v.get("companies") or []]} for v in out_vc]
    # v55 (R55): theme membership decided apart from, and before, any layer: a company whose principal business is a kind of product the
    # theme's definition (its name and its map's own layers) doesn't include is screened out, never kept in "Other" (theme_check.off_scope)
    from .theme_check import off_scope, off_scope_listed
    stext = scope_text(theme, m.get("sector") or "", own)

    def scope_of(s_, text):
        """its principal business in its own words; with none stored, its official industry, else its listed name (off_scope_listed)."""
        c_ = by_sym.get(s_) or {}
        words = about_of(s_) or c_.get("what")
        if words and not str(words).startswith(FILING_TITLES):
            return off_scope(words, text, c_.get("name") or "")
        return off_scope_listed(c_.get("name") or "", c_.get("industry") or facts_for(s_).get("industry") or "", text)
    out_vc, off = without_off_industry(out_vc, {c.get("ticker") for c in todo}, evidence, off_before,
                                       lambda s_: about_of(s_) or (by_sym.get(s_) or {}).get("what"),
                                       scope=lambda s_: scope_of(s_, stext))
    placements = m.get("placements")
    out_vc, sure = confirmed_by_words(out_vc, about_of, theme)
    if sure and placements is not None:
        placements = {**placements, "confirmed": (placements.get("confirmed") or 0) + sure,
                      "unconfirmed": max(0, (placements.get("unconfirmed") or 0) - sure)}
    # v55 (R55): the theme's members first, then their layers: a contract manufacturer or component supplier of the theme's products left in
    # "Other" goes to a layer of that kind, named from the theme's words, when there are enough of them, else is said to be one there
    out_vc, fallback = fallback_layer(out_vc, words_of, theme)
    # t56 (R55 review: the live R55 Metals deck lost "Aluminium" (13 companies) again and Consumer retail "Catalog and mail-order houses" (6),
    # their companies to "Other", informative 52 of 66 to 39 of 66 and 75 of 98 to 69 of 98): the taxonomy guard, the last step after every
    # rule that moves companies (c54's restore ran before the stage, scope and fallback rules, and read its own restore's moves in the change
    # log back as moves out of the layer): against the previous published version, a named layer of LOST_MIN companies or more that is gone
    # comes back with its companies that still fit (restore_vanished), then a fall of GUARD_FALL points or more in the informative share
    # sends back to their layer the companies of "Other" whose words still say what it sells (share_guard); each said in the placements
    gone_layers: list = []
    share_row = None
    if previous or moved_before or moved_out:
        # r62 (the R62 replay of the live R60 Fertilizers and agrochemicals input: "Industrial gases", 5 companies published, 3 of them in the
        # map's previous names, lost unsaid): a layer's companies are counted from the published memory too, every member of it
        lost_from = {**(published or {}), **(previous or {})} if published else (previous or {})
        out_vc, gone_layers = restore_vanished(out_vc, lost_from, evidence, theme, theme_words=kind_stems(theme), moved_before=moved_before,
                                               moved_out=moved_out)
        out_vc, share_row = share_guard(out_vc, previous or {}, evidence, theme, theme_words=kind_stems(theme), moved_before=moved_before,
                                        moved_out=moved_out)
    # p57 (R56 review): the placement contract, after every rule: a truthful name for each layer a rule made (or none made), then every
    # published member held in its published layer unless printed evidence moved it
    # the contract's steps run where the placement reads the published memory (`published`, {} for a theme read for the first time: every
    # live placement, theme_routes.placed); a replay of a stored version without it places as that version's rules did
    truth, fit_rows, held_rows, fit_answer, audit_rows, audit_answer, scale_rows = [], [], [], None, [], None, []
    if published is not None:
        # r58 (R58, the owner's review of the live R57.2 Consumer retail deck: "Single-category specialty retailers", 9 companies in R56, lost
        # again because the published version, R57.2's, no longer had it): a layer counts as published when any earlier published version had
        # it, read from the change log's moves out of a layer the snapshot no longer has (previous_published)
        out_vc, truth = truthful_layers(out_vc, previous_published(published, moved_before, moved_out, theme), evidence, theme)
        out_vc, whole_out = whole_company_out(out_vc, words_of, theme)
        if whole_out:
            off = list(off or []) + [{"ticker": x["ticker"], "name": x["name"], "industry": x["industry"], "why": x["why"]} for x in whole_out]
        out_vc, fit_rows, fit_answer = misfit_moves(out_vc, evidence, theme, words_of, ask,
                                                    kept.get("fit") if isinstance(kept.get("fit"), dict) else None)
        out_vc, audit_rows, audit_answer = audit_moves(out_vc, evidence, theme, words_of, ask,
                                                       kept.get("audit") if isinstance(kept.get("audit"), dict) else None)
        out_vc, scale_rows = scale_moves(out_vc, words_of, theme, figures_for if figures_of is not None else None)
        out_vc, held_rows = hold_published(out_vc, published, evidence, theme)
        out_vc, compute_rows = compute_fit(out_vc, words_of, theme)
        out_vc, property_rows = property_moves(out_vc, words_of)          # r68e: a property owner in the layer of the kind its words name
        compute_rows = compute_rows + property_rows
        out_vc, business_rows = business_moves(out_vc, words_of, theme, published, moved_before)    # r69e: what it sells now, in its words
        compute_rows = compute_rows + business_rows
        out_vc, off_compute_rows = off_theme_compute(out_vc, theme)
        compute_rows = compute_rows + off_compute_rows
        out_vc, unsaid_rows = unsaid_moves(out_vc, words_of, theme, published)
        compute_rows = compute_rows + unsaid_rows
        out_vc, other_rows = words_from_other(out_vc, words_of, theme)
        # r60: a way of earning never takes a company out of a layer its words name; a retail format apart from brand ownership; a kind of
        # business beside the theme's (an established pharmaceutical company among biotechs) in a layer of its own
        out_vc, how_rows = by_how_back(out_vc, words_of, theme, published)
        out_vc, format_rows = format_moves(out_vc, words_of, theme)
        out_vc, kind_rows = kind_apart(out_vc, words_of, theme)
        other_rows = other_rows + how_rows + format_rows + kind_rows
        out_vc, single_rows = single_layers(out_vc, words_of, theme, previous_published(published, moved_before, moved_out, theme))
        out_vc, printed_rows = printed_names(out_vc, words_of)
        truth = truth + printed_rows
        # r62: a company its own filings show to be a domestic filer is never in a layer of foreign companies
        out_vc, home_rows = domicile_moves(out_vc, facts_for)
        other_rows = other_rows + home_rows
        # r59: a layer never mostly listed and left out, a company moved in on no line of its words back where it was
        out_vc, listed_rows = listed_out(out_vc, words_of, theme, moved_before, figures_for if figures_of is not None else None, published)
        out_vc, bar_rows = kind_bars(out_vc, words_of, theme)          # e81: a kind of company a layer can never hold
        single_rows = single_rows + listed_rows + bar_rows
        single_rows = other_rows + single_rows
        held_rows = held_rows + compute_rows + single_rows
    back = [{"ticker": s_, "name": (by_sym.get(s_) or {}).get("name") or (off_before or {})[s_][0],
             "why": "an earlier version found its own words describe another business; its own words read now show the theme's work"}
            for s_ in sorted(off_before or {}) if s_ in {c.get("ticker") for v in out_vc for c in v.get("companies") or []}
            and (about_of(s_) or (by_sym.get(s_) or {}).get("what"))]
    if back:
        placements = {**(placements or {}), "back": back}
    if gone_layers:          # c54: each named layer of the previous version a re-check would have lost, restored or with why not
        placements = {**(placements or {}), "layers_gone": gone_layers}
    if share_row:            # t56: the informative share fell by GUARD_FALL points or more: what the guard sent back, and why the rest stayed
        placements = {**(placements or {}), "share_guard": share_row}
    # e81 (the owner's review of the R79 decks, P1: property-development layers in Fertilizers and Textiles): a layer of property or real
    # estate in a theme that names no such business is said as a theme-scope warning, with its companies, whatever kept it
    scope_warn = [{"layer": _HALF_RX.sub("", v["layer"]), "companies": [c.get("ticker") for c in v.get("companies") or []]}
                  for v in out_vc if not v.get("official") and v.get("layer") and v.get("companies")
                  and property_scope_layer(v["layer"], f"{theme} {m.get('sector') or ''}")]
    if scope_warn:
        print("theme base: theme-scope warning:", theme[:40], [x["layer"] for x in scope_warn])
        placements = {**(placements or {}), "scope_warning": scope_warn}
    if placements is not None and placements.get("dropped") and published is not None:
        out_vc, placements = layer_answer_removals(out_vc, placements, words_of, theme, facts_for)
    if placements is not None and placements.get("dropped"):
        # p57 (lane g57: 60 companies in 20 themes carried a business-membership removal while still in the theme, Sarepta in "Other"):
        # a company the check left out of a map group that is still in the theme was moved, never removed: its answer is a layer decision
        inside = {c.get("ticker") for v in out_vc for c in v.get("companies") or []}
        gone = [x for x in placements["dropped"] if not (isinstance(x, dict) and x.get("ticker") in inside)]
        layer_no = [x for x in placements["dropped"] if isinstance(x, dict) and x.get("ticker") in inside]
        if layer_no:
            placements = {**placements, "layer_no": list(placements.get("layer_no") or []) + layer_no}
            if gone:
                placements["dropped"] = gone
            else:
                placements = {k: x for k, x in placements.items() if k != "dropped"}
    if truth or held_rows or fit_rows or audit_rows or scale_rows:   # p57: the contract's steps (r571: the scale rule)
        placements = {**(placements or {}), "contract": {**({"layers": truth} if truth else {}), **({"fit": fit_rows} if fit_rows else {}),
                                                        **({"scale": scale_rows} if scale_rows else {}),
                                                        **({"audit": audit_rows} if audit_rows else {}),
                                                        **({"held": held_rows} if held_rows else {})}}
    elif isinstance(placements, dict) and "contract" in placements:
        # r60: the contract says this placement's steps; one handed on from the stored check (a company "moved to Other" an earlier
        # placement made) is never said again by a placement that made no such step
        placements = {k: x for k, x in placements.items() if k != "contract"}
    if staged_n:             # v55: companies displayed in the layer of their own stage
        placements = {**(placements or {}), "stage_moved": staged_n}
    if fallback:             # v55: the adjacent-kind layer made, or the line said in "Other"
        placements = {**(placements or {}), "fallback": fallback}
    if off:
        placements = {**(placements or {}), "off_industry": off}
        for k_ in ("placed", "total", "base"):
            if isinstance(placements.get(k_), int):
                placements[k_] = max(0, placements[k_] - len(off))
    return {**m, "value_chain": out_vc, **({"placements": placements} if placements is not None else {})}, {"assign": got, "rename": rename, "extra": extra, **({"names_for": names_for} if names_for else {}),
                                          **({"models": models} if models is not None else {}), **({"model_names": model_names} if model_names else {}),
                                          **({"model_tags": tags} if models is not None and tags else {}),
                                          **({"model_confidence": conf} if models is not None and conf is not None else {}),
                                          **({"reasked": reasked} if reasked else {}),
                                          **({"fit": fit_answer} if fit_answer else {}),
                                          **({"audit": audit_answer} if audit_answer else {}),
                                          **({"reasked_rules": RULES} if reasked and published is not None and ask is not None else
                                             {"reasked_rules": kept["reasked_rules"]} if kept.get("reasked_rules") else {})}


# ---------- gl50 (R50): a company's fit to its layer by what the layer is, not only by how it earns ----------
# The rotating review of six unseen themes: Gillette and P&G Hygiene in "Branded packaged foods", Nestle India and a sugar maker in "Beverage
# bottling", a sugar and nutraceuticals maker and a personal care maker in "Cigarette and tobacco", an edible oil refiner in "Branded packaged
# foods": each passed as "of the layer's kind" on its way of earning alone (making its own products). A placement is now also checked against
# what the layer is (its name) in the company's own words, and against its official industry.
_PARTS = re.compile(r",|&|/|\band\b|\bor\b", re.I)


def _fit_words(text) -> set[str]:
    """A text's words of what is made or done (kind_stems keeps them), each in lower case without a plural "s", for words_fit."""
    out = set()
    for w in re.findall(r"[a-z0-9]+", _short_joined(text)):
        if len(w) >= 3 and kind_stems(w):
            out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def _same_word(a: str, b: str) -> bool:
    """Two words the same, or sharing their first seven letters ("refrigerant" and "refrigeration"); never "synthetic" for "synthesis" or
    "engineering" for "engines" (five letters said those)."""
    return a == b or (min(len(a), len(b)) >= 7 and a[:7] == b[:7])


def distinct_stems(v: dict, layers: list[dict], theme_words: set) -> list[set]:
    """What a layer's name (its shown name, a half's "(larger)" left out) says it is apart from the map's other layers, each of its parts
    apart ("Engines and industrial machinery makers": engines, or industrial machinery): each part's words of what is made or done
    (_fit_words), less the theme's words and those another layer's name says too. [] when no part says anything of its own."""
    name = lambda x: _HALF_RX.sub("", x.get("layer") or "")      # noqa: E731
    others = set().union(*[whole_stems(name(w)) for w in layers if w is not v and name(w) != name(v)] or [set()])
    parts = [{w for w in _fit_words(p) if not (kind_stems(w) & theme_words) and not any(_near(_stem(w), b) for b in others)
              and w not in GENERIC_FIT and f"{w}s" not in GENERIC_FIT}          # gl52: "healthcare" says nothing of which layer
             for p in _PARTS.split(name(v))]
    return [x for x in parts if x]


def words_fit(parts: list, text: str) -> bool:
    """Whether a company's words say more than half of one part of a layer's distinct words (distinct_stems): "grooming and oral care ...
    packaged consumer goods" says one of "packaged" and "foods", which is not the layer's kind; "diesel engines" says "engines"."""
    mine = _fit_words(text)
    return any(sum(1 for b in x if any(_same_word(a, b) for a in mine)) * 2 > len(x) for x in parts)


def industry_named_by(v: dict, industry, theme_words: set) -> bool:
    """Whether a layer's name (its shown or map name) or its description says all that one part of an official industry's plain name says
    (industry_named: "Compressors, Pumps & Diesel Engines" by "engines, compressors and process equipment"); an industry naming no one
    business ("Diversified", "Other") is named by none."""
    if not industry or re.search(NO_ONE_BUSINESS, plain_industry(industry), re.I):
        return False
    parts = [p for p in _PARTS.split(plain_industry(industry)) if kind_stems(p) - theme_words] or [plain_industry(industry)]
    return any(industry_named(x, p, theme_words) for x in (_HALF_RX.sub("", v.get("layer") or ""), v.get("was"), v.get("description")) if x
               for p in parts)


def industry_fits(v: dict, industry, theme_words: set) -> bool:
    """Whether a company's official industry is its layer's: the layer names it (industry_named_by), or it is the industry of most of the
    layer's companies that have one."""
    if industry_named_by(v, industry, theme_words):
        return True
    if not industry or re.search(NO_ONE_BUSINESS, plain_industry(industry), re.I):
        return False
    inds = [key(c.get("industry")) for c in v.get("companies") or [] if c.get("industry")]
    return bool(inds) and inds.count(key(industry)) * 2 > len(inds)


# words of any sentence, no kind of business (says_of_layer reads a layer's whole description)
_FIT_STOP = {_stem(w) for w in ("under", "but", "when", "while", "where", "its", "own", "allow", "allows", "also", "more", "most", "into", "over",
                                "about", "both", "each", "many", "much", "only", "than", "then", "very", "after", "before", "between", "within",
                                "without", "well", "high", "higher", "low", "lower", "new", "rise", "rises", "fall", "falls", "increase", "increases",
                                "established", "strength", "squeeze", "against", "because", "since", "along", "based", "major", "various", "wide",
                                "demand", "growth", "long", "short", "term", "terms", "year", "years", "time", "times", "segment", "segments",
                                "set", "help", "helps", "keep", "keeps", "make", "made", "work", "works", "use", "used", "uses", "need", "needs")}


# gl52 (R52, the rotating review of Release 51: Novo Nordisk moved into "Bioprocessing suppliers and diversified healthcare" because its words
# say "healthcare"; AbbVie and Gilead kept in "Research tools and diagnostics suppliers" because its description says the tools are "sold to labs
# and drug developers"): words any company of any layer may use, which say nothing of which layer it is of, and the customers a description
# names, which are not what the layer's companies make or do
GENERIC_FIT = {"healthcare", "health", "industrial", "industrials", "technology", "technologies", "platform", "platforms", "develop", "developer",
               "developers", "development", "developing", "innovative", "advanced", "leading", "diversified", "solution", "solutions", "global"}
_FIT_STOP |= {_stem(w) for w in GENERIC_FIT}
_CUSTOMERS = re.compile(r"\b(?:sold|sells?|selling|supplied|supplies|supplying|serv(?:es|ing|ed)?|cater(?:s|ing)?|used by|bought by)\s+(?:to\s+)?"
                        r"(?:[\w-]+\s+){0,1}(?:labs?|hospitals?|customers?|clients?|businesses|companies|makers?|developers?|manufacturers?|"
                        r"governments?|retailers?|consumers?|oems?|[\w-]+\s+(?:makers?|developers?|companies|manufacturers?))\b[^.;]{0,80}", re.I)


# what a description says the layer's companies are not ("set apart by tool and assay sales rather than drug sales")
_CONTRAST = re.compile(r"\b(?:rather than|instead of|unlike|as opposed to|apart from|other than|not)\b[^.;]{0,80}", re.I)


def says_of_layer(v: dict, text: str, theme_words: set) -> bool:
    """Whether a company's words share a word of what it makes or does (kind_stems) with its layer's description, beyond its name's words:
    the loosest sign its words are of the layer's kind (a coffee maker's "coffee" shares nothing with "biscuits, noodles, snacks and dairy").
    gl52: never a word any company may use (GENERIC_FIT), nor one of the customers the description names (_CUSTOMERS)."""
    names = whole_stems(" ".join(str(x) for x in (_HALF_RX.sub("", v.get("layer") or ""), v.get("was")) if x))
    lay = whole_stems(_CONTRAST.sub(" ", _CUSTOMERS.sub(" ", str(v.get("description") or "")))) - theme_words - names - _FIT_STOP       # the name is words_fit's: more than half of it
    mine = whole_stems(text) - theme_words - _FIT_STOP
    return any(_near(a, b) for a in mine for b in lay)


# c54 (R53, the owner's review of the live R53 decks: Intel, a chip maker, moved into "Chip equipment and subsystem suppliers" (its words share
# "chip" and "components" with the layer's prose); Indo National, a battery and flashlight maker, into "Branded packaged foods manufacturing"
# (it "sells products under the brand"); UFP Technologies, a contract and components maker, into "Surgical robotics systems"): a company joins
# a layer by how it earns only on evidence that it sells what the layer's name defines, read in the sentences of its own words that say what it
# does, never a word its long description shares with the layer's prose, nor an industry most of the layer's companies happen to share.
SOLD_SENTENCES = 2               # sentences of a company's own words read for what it sells (those that say what it does)
# words naming a part of a larger product: "subsystems" says what a layer sells only with the product they are part of (the layer's description)
PART_WORDS = {"subsystem", "component", "part", "module", "accessory", "accessorie", "assembly", "assemblie", "consumable", "kit", "spare", "unit"}
# ...and words naming a category of goods any trade has ("turn-key equipment" of optical networks says nothing of chip-making equipment)
CATEGORY_WORDS = {"equipment", "machinery", "machine", "tool", "device", "instrument", "system", "product", "material", "solution", "hardware",
                  "apparatu", "apparatus"}
_LED_WORDS = {"led", "based", "focused", "driven", "oriented", "linked", "backed", "owned", "run", "centric"}     # "X-led": driven by X
_SOLD_PLAIN = {_stem(w) for w in PART_WORDS | CATEGORY_WORDS | {f"{w}s" for w in PART_WORDS | CATEGORY_WORDS}} | \
    {_stem(w) for w in ("build", "builds", "built", "builder", "builders", "go", "goes", "use", "uses", "run", "runs", "earn", "earns", "those",
                        "plus", "firms", "companies", "design", "designs", "designer", "designers", "into", "own", "plant", "plants",
                        "factory", "factories", "facility", "facilities", "recurring", "contract", "contracts", "established", "base")}


def sold_text(evidence, name: str = "") -> str:
    """What a company's own words say it makes, sells or does: the first SOLD_SENTENCES sentences of its own words (own_text) that say what
    it does (one_line's reading: a founding-history opening and results lines skipped), the customers and contrasts they name and the words of
    its own name left out. "" with no words of its own."""
    t = own_text(evidence)
    if no_words(t):
        return ""
    t = " ".join(_HEADING.sub(". ", _MARKUP.sub(" ", _GLUED.sub(r"\1 \2 \3", without_name(t, name)))).split())
    picks = []
    for x in _sentences(t):
        x = _HISTORY.sub("", x).strip(" ,;:-–—")
        if _FORMER.match(x):          # r69e: "Historically, it manufactured cement" is no word of what it sells now
            continue
        if len(x) >= 15 and not _PRESS.search(x) and _DOES.search(x):
            picks.append(x)
        if len(picks) >= SOLD_SENTENCES:
            break
    lead = " ".join(picks) or one_line(t)
    return _CONTRAST.sub(" ", _CUSTOMERS.sub(" ", _MARKETS.sub(" ", lead)))


# r69e: words of a layer's name that say its companies' scale, reach or structure, no kind of product ("Regional integrated producers")
_STRUCTURE_WORDS = {"regional", "national", "pan", "india", "indian", "integrated", "producers", "producer", "makers", "maker", "manufacturers",
                    "manufacturer", "companies", "company", "players", "player", "larger", "smaller", "large", "small", "mid", "sized", "and",
                    "of", "the", "leading", "major", "other", "diversified", "listed", "firms", "groups", "group"}


# r69e (LIVE13A-001): a sentence of what a company did before ("Historically, BCL manufactured Portland Slag Cement") says no business it runs
_FORMER = re.compile(r"\s*(?:historically|formerly|previously|earlier|in the past|until\s+(?:\w+\s+)?\d{4}|prior to\s+(?:\w+\s+)?\d{4})\b", re.I)


# the markets a company says it serves are its customers', not what it sells ("The product segments we target include ... surgical")
_MARKETS = re.compile(r"\b(?:the\s+)?(?:product\s+)?(?:segments?|markets?|end[- ]markets?|industries|sectors|verticals)\b[^.;]{0,40}?\b(?:we|it|they|the "
                      r"company)\s+(?:target|serve|address|sell into|operate in|operate)\b[^.;]*", re.I)


def theme_product(name: str, theme_words: set) -> bool:
    """c54: whether a layer's name sells the theme's own product, only qualified ("Specialty and performance chemicals" in Chemicals,
    "Branded home, personal care and FMCG"): the last word of what it names (its head) is the theme's own word, so the name sets no product
    of its own apart from the theme's (its qualifiers are a matter of degree, not of what is sold)."""
    words = [w for w in re.findall(r"[a-z0-9]+", str(name or "").lower()) if kind_stems(w)]
    return bool(words) and bool(kind_stems(words[-1]) & theme_words)


def _name_parts(name: str) -> list[list[str]]:
    """c54: each part of a layer's name ("Chip equipment and subsystem suppliers": "Chip equipment", "subsystem suppliers") as its words of
    what is sold, in order, each in lower case without a plural "s" (words of how any company earns and "-led" left out): its last word is
    what the part names (its head), the words before it qualify it."""
    out = []
    for p in _PARTS.split(_short_joined(_HALF_RX.sub("", str(name or "")))):
        ws = [w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith("ss") else w for w in re.findall(r"[a-z0-9]+", p)
              if len(w) >= 3 and kind_stems(w)]
        ws = [w for w in ws if w not in _LED_WORDS]
        if ws:
            out.append(ws)
    return out


def _says(mine: set, w: str) -> bool:
    return any(_same_word(a, w) or _near(_stem(a), _stem(w)) for a in mine)


def _alike(a: str, b: str) -> bool:
    """Two stems of one word, a plural of a short one too ("fab", "fabs")."""
    return _near(a, b) or a + "s" == b or b + "s" == a


# r69e (LIVE13A-001, the live R67 Semiconductors log: OSI Systems, "a vertically integrated designer and manufacturer of specialized electronic
# systems" for airport security, moved into "Fabless chip design" because "designer" says the name's last word): a head naming an act any
# trade does (design, manufacturing, testing, services...) is said only with what it is done to: a word of the part before it ("fabless"), or,
# where that word is the theme's own ("chip"), a theme word the company's words say ("semiconductor"); and "vertically integrated" says how a
# company is organised, never the "integrated" of "integrated device makers"
ACT_HEADS = {"design", "designing", "manufacturing", "manufacture", "making", "production", "service", "servicing", "test", "testing",
             "assembly", "distribution", "trading", "processing", "engineering"}
_ORGANISED = re.compile(r"\b(?:vertically|fully|horizontally|backward(?:ly)?|forward)[- ]integrated\b", re.I)


# e77 (the live R76 Semiconductors deck, LIVE13A-001 / LIVE14A-002: OSI Systems, "security and inspection systems such as airport security
# X-ray machines ... and optoelectronic devices", kept in "Fabless chip design" by "its official industry or way of earning": the way of
# earning an answer read off its official industry alone, "fabless" at medium confidence, never said by its words): a layer's name that states
# a way of earning takes a company by that way only where its own words state it or name the theme's own product as what it sells; with
# words of its own that say neither, the way of earning is a reading of its industry, never evidence of what it sells
def model_said(text: str, model: str, theme_words: set) -> bool:
    """Whether a company's words (sold_text) bear out a way of earning read for it: none to judge by, or words stating that way of earning
    (theme_check.stated_model) or naming what it is of (theme_check.MODEL_OF: a fabless company's chips, "graphics processors"), or words
    naming the theme's own product as what it sells (says_theme_product)."""
    from .theme_check import MODEL_OF, stated_model
    t = _ORGANISED.sub(" ", str(text or "")).strip()
    return (not t or stated_model(t) == model or bool(MODEL_OF.get(model) and re.search(MODEL_OF[model], t, re.I))
            or says_theme_product(t, theme_words))


def sells_layer(v: dict, layers: list[dict], text: str, industry, theme_words: set, model: str = "", described: bool = True) -> bool | None:
    """c54: whether a company sells what a layer's name defines, read in its words of what it sells (sold_text) or its official industry's
    name, part by part of the name ("Chip equipment and subsystem suppliers": chip equipment, or subsystems): a part's head ("foods",
    "formulation", "intermediate") said; a head naming a category any trade has ("equipment", "systems", "devices": CATEGORY_WORDS) only with
    the word that qualifies it ("robotics systems": robotic), or, qualified only by the theme's own word ("chip equipment" in Semiconductors),
    with something its description's first sentence says they make ("lithography", "test machines"); a head naming a part of a larger product
    ("subsystems": PART_WORDS) only with that product (the name's other head, else the description's). Also two of the things the description's
    first sentence says they make (`described`), or a part of the name that states the way of earning its evidence shows (`model`: "Fabless
    chip design" for a fabless chip designer). None when the name sells the theme's own product only qualified (theme_product), or names
    nothing (nothing to judge by)."""
    from .theme_check import stated_model
    from .theme_library import WORDS
    names = [nm for nm in dict.fromkeys((_HALF_RX.sub("", v.get("layer") or ""), v.get("was"))) if nm]
    pf = [property_fit(nm, text) for nm in names]          # r68e: a property owner's layer by the kind of property its words name
    if True in pf or (pf and all(x is False for x in pf)):
        return True in pf
    parts = [p for nm in names for p in _name_parts(nm)]
    if not parts or any(theme_product(nm, theme_words) for nm in names):
        return None
    if model and any(stated_model(p) == model for nm in names for p in _PARTS.split(nm)) and model_said(text, model, theme_words):
        return True
    own = lambda w: bool(kind_stems(w) & theme_words) or bool(kind_stems(WORDS.get(w, "")) & theme_words)      # noqa: E731  (the theme's word)
    first = (_sentences(" ".join(str(v.get("description") or "").split())) or [""])[0]
    lay = whole_stems(_CONTRAST.sub(" ", _CUSTOMERS.sub(" ", first))) - theme_words - _FIT_STOP - _SOLD_PLAIN
    heads = [p[-1] for p in parts]

    def fits(mine: set, said: set) -> bool:
        if not mine:
            return False
        for p in parts:
            head, quals = p[-1], [w for w in p[:-1] if not own(w)]
            if head in PART_WORDS:
                whole = [h for h in heads if h != head and h not in PART_WORDS]
                if _says(mine, head) and (any(_says(mine, h) for h in whole) or any(_alike(a, b) for a in said for b in lay)):
                    return True
            elif head in CATEGORY_WORDS:
                if quals:
                    if _says(mine, quals[-1]):
                        return True
                elif _says(mine, head) and any(_alike(a, b) for a in said for b in lay):
                    return True
            elif not own(head) and _says(mine, head):
                if head in ACT_HEADS and not (any(_says(mine, q) for q in quals)
                                              or ((not quals or len(quals) < len(p) - 1) and any(own(w) for w in mine))):
                    continue
                return True
        return described and len({b for b in lay if any(_alike(a, b) for a in said)}) >= 2
    text = _ORGANISED.sub(" ", text or "")
    if text and fits(_fit_words(text), whole_stems(text) - theme_words - _FIT_STOP - _SOLD_PLAIN):
        return True
    plain = plain_industry(industry) if industry else ""
    if plain and not re.search(NO_ONE_BUSINESS, plain, re.I) and fits(_fit_words(plain), set()):
        return True
    return False


def refits_kept(vc: list[dict]) -> list[dict]:
    """gl50: a company definition_fit moved keeps its "refit" only where it still is (the split by how companies earn may move it on, with its
    own reason); the layer's map name, its shown name or a half's, or "" for "Other"."""
    def here(v):
        return "" if v.get("official") else _HALF_RX.sub("", v.get("layer") or "")
    out = []
    for v in vc:
        cos = v.get("companies") or []
        if any(isinstance(c.get("refit"), dict) for c in cos):
            names = {here(v), _HALF_RX.sub("", v.get("was") or "")} - ({""} if not v.get("official") else set())
            cos = [c if not isinstance(c.get("refit"), dict) or c["refit"].get("to", "") in names else {k: x for k, x in c.items() if k != "refit"}
                   for c in cos]
            v = {**v, "companies": cos}
        out.append(v)
    return out


def without_name(text: str, name: str) -> str:
    """A company's words with the words of its own name left out ("Ajax Engineering Limited manufactures concrete equipment": its name's
    "Engineering" says nothing of what it makes)."""
    drop = {w.lower() for w in re.findall(r"[A-Za-z0-9]+", name) if len(w) >= 3}
    return "".join(w for w in re.split(r"(\s+)", str(text or "")) if re.sub(r"[^a-z0-9]", "", w.lower()) not in drop).strip() if drop else text


def definition_fit(vc: list[dict], evidence, theme: str, about_of=None) -> list[dict]:
    """The map's layers with each company that fits neither what its layer is nor its industry moved (gl50, R50). A company fits its layer
    when its own words (own_text, else its line on the page) say more than half of the layer name's distinct stems (words_fit) or share a word
    of its kind with the layer's name or description (says_of_layer), or when its official industry is the layer's (industry_fits). One that
    fits by none goes to the one other layer its words say (words_fit), else to the one layer whose name or description names its industry
    (industry_named_by), else, with words of its own, to "Other"; with none, it stays (nothing to judge it by). Only a company placed by its
    words alone ("placed": "words": no AI answer read it against the layers) is checked: never the map's own picks, a company the AI's
    answer placed or whose words were checked for the layer ("verified"), the companies of a layer whose name states no kind of its own or
    that the split made by how its companies earn, or "Other".
    Each moved company carries "refit": {"from": its layer, "why": the reason, said}."""
    tw = kind_stems(theme)
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    if len(own) < 2:
        return vc
    stems = {id(v): distinct_stems(v, own, tw) for v in own}
    # gl52: the map's earlier name for a layer says what it is too (the description's own words are left to words_fit of that name)
    was_stems = lambda v: distinct_stems({"layer": v["was"]}, own, tw) if v.get("was") else []      # noqa: E731
    moves: list[tuple] = []
    unfit: dict = {}
    for v in own:
        if not stems[id(v)] or v.get("by_model"):
            continue
        for c in v.get("companies") or []:
            # gl52 (R52, the rotating review of Release 51: Shopify and Twilio in "Cloud and AI compute providers", Medtronic and 3M in
            # "Surgical robotics systems", placed by the AI's answer, never checked against what the layer is): the AI's placements and
            # the map's own picks not confirmed by their words are checked too, but move only on words of their own (never on none)
            ai_ = c.get("placed") == "ai" or (not c.get("placed") and not c.get("moved") and not c.get("by_map"))
            if c.get("verified") or (c.get("placed") != "words" and not ai_):
                continue                # a placement confirmed by the company's own words is never moved
            words = own_text(evidence(c.get("ticker"))) if evidence else ""
            if ai_ and about_of is not None:            # gl52: its whole stored description, never the model evidence's 420 characters
                try:
                    words = own_text(about_of(c.get("ticker")) or "") or words
                except Exception:
                    pass
            if no_words(words) and c.get("what") and not str(c.get("what")).startswith(FILING_TITLES):
                words = str(c.get("what"))
            words = "" if no_words(words) else without_name(words, c.get("name") or "")
            if ai_ and not words:
                continue
            ind = c.get("industry") or ""
            if (words and (words_fit(stems[id(v)], words) or says_of_layer(v, words, tw) or (ai_ and words_fit(was_stems(v), words)))) \
                    or industry_fits(v, ind, tw):
                continue
            names = lambda xs: list(dict.fromkeys(_HALF_RX.sub("", x["layer"]) for x in xs))      # noqa: E731
            lead = one_line(words) or words         # a move rests on what its first sentence says it does, never a list of uses or customers
            if ai_:
                # gl52: an AI placement or a map pick whose own words and official industry both contradict what its layer is stays where the
                # answer put it, listed but left out of the layer's figures as another business ("unfit"), never moved to "Other" on a loose read
                # the contradiction is shown only by another layer the company is of by both: its official industry and its words saying that
                # layer's name; with none, nothing contradicts the answer (a long description that misses the layer's words proves nothing)
                # (bounded: the answer's layer is kept, so no layer's membership moves; only its figures leave such a company out)
                here_ = _HALF_RX.sub("", v["layer"])
                both_ = [w for w in own if w is not v and industry_fits(w, ind, tw) and (words_fit(stems[id(w)], words) or words_fit(was_stems(w), words))]
                if both_:
                    unfit[id(c)] = (here_, f"its own words don't say what “{here_}” is, nor does its official industry"
                                           + (f" ({plain_industry(ind)})" if ind else "") + f"; both are of “{names(both_)[0]}”")
                continue
            by_words = [w for w in own if w is not v and words and words_fit(stems[id(w)], lead)]
            by_ind = [w for w in own if w is not v and industry_named_by(w, ind, tw)]
            here = _HALF_RX.sub("", v["layer"])
            if len(names(by_words)) == 1:
                to = by_words[0]
                why = f"its own words say what “{names(by_words)[0]}” is, not what “{here}” is"
            elif not by_words and len(names(by_ind)) == 1:
                to = by_ind[0]
                why = (f"its own words don't say what “{here}” is" if words else "no words of its own") + \
                      f"; its official industry, {plain_industry(ind)}, is what “{names(by_ind)[0]}” names"
            elif words:
                to = None
                why = f"its own words don't say what “{here}” is, nor does its official industry" + (f" ({plain_industry(ind)})" if ind else "")
            else:
                continue
            moves.append((v, c, to, why))
    def with_unfit(layers):
        if not unfit:
            return layers
        return [{**v, "companies": [{**c, "unfit": {"layer": unfit[id(c)][0], "why": unfit[id(c)][1]}} if id(c) in unfit else c
                                    for c in v.get("companies") or []]} if not v.get("official") else v for v in layers]
    if not moves:
        return with_unfit(vc)
    gone = {id(c) for _, c, _, _ in moves}
    pos = {id(v): i for i, v in enumerate(vc)}
    out = [{**v, "companies": [c for c in v.get("companies") or [] if id(c) not in gone]} for v in vc]       # never the caller's layers
    other = next((x for x in out if x.get("official") and x.get("basis") == "rest"), None)
    for v, c, to, why in moves:
        moved = {**c, "refit": {"from": _HALF_RX.sub("", v["layer"]), "to": _HALF_RX.sub("", to["layer"]) if to is not None else "", "why": why}}
        if to is not None:
            out[pos[id(to)]]["companies"].append({**moved, "fit": True})
            continue
        if other is None:
            other = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
            out.append(other)
        moved.pop("fit", None)
        other["companies"] = list(other["companies"]) + [moved]
    return with_unfit(out)


def confirmed_by_words(vc: list[dict], about_of, theme: str) -> tuple[list[dict], int]:
    """(the layers, how many companies they confirm) (c1, R44: the live Release 43 Insurance deck listed PB Fintech, the map's own pick for
    "Distribution and aggregation", as "not confirmed", its words said to "describe other work", because the check of its words timed out):
    a company the AI added from another industry into one of the map's own layers (never one placed after the map) whose own words say what
    that layer's name says ("distributing and servicing financial products" says "Distribution") is in the theme by its own words: confirmed
    ("verified", "verified_by": "words"), whatever check did not answer. Which comparisons it is in is decided apart (by_model, calc_record):
    a distributor in its own layer is never among the underwriters."""
    tw = kind_stems(theme)
    n, out = 0, []
    for v in vc:
        if v.get("official") or v.get("by_model") or v.get("industry_group"):
            out.append(v)
            continue
        cos = []
        for c in v.get("companies") or []:
            if not c.get("base", True) and not c.get("verified") and not c.get("placed") and not c.get("moved"):
                words = own_text(about_of(c.get("ticker")) or c.get("what") or "")
                name = v.get("was") or v.get("layer") or ""
                head = next((_stem(w) for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 4 and w not in _PLAIN), "")
                # its words say a word of what the name says is done (name_says), or the name's head word ("Distribution", a way of earning
                # name_says leaves to the models)
                if words and not no_words(words) and (name_says(name, words, tw)[1] or (head and head in _stems(words))):
                    c = {**c, "verified": True, "verified_by": "words"}
                    n += 1
            cos.append(c)
        out.append({**v, "companies": cos})
    return out, n


def scope_text(theme: str, sector: str, own: list[dict]) -> str:
    """v55: a theme's definition as its own words state it: its name, its sector's and its map's own layers' names (and former names) and
    descriptions (never an official industry's name: an industry files companies of other businesses too)."""
    return " ".join([str(theme or ""), str(sector or "")] + [f"{v.get('layer') or ''} {v.get('was') or ''} {v.get('description') or ''}"
                                                              for v in own if not v.get("official")])


def without_off_industry(vc: list[dict], todo: set, evidence, before: dict | None = None, words=None, scope=None) -> tuple[list[dict], list[dict]]:
    """(the layers without the companies of another business, those companies) (R40, the owner's review of the live Release 39 decks: solar
    makers in "Other semiconductor companies", propane distributors in "Other consumer retail companies"): a company the theme's official
    industry brought in (`todo`: placed after the map, never one the map named) whose own words describe another business than the one
    that industry files it under (theme_check.off_industry) is no member of the theme: dropped from every layer and from "Other", and named
    once, with the industry it is filed under ({"ticker", "name", "industry"}), so the theme's coverage says who was left out and why. A
    group left with no company is dropped.
    d53 (R53, the owner's review of the live R52 Consumer retail deck: Suburban Propane, a propane distributor dropped as another business
    since R40, among the companies "added" when its stored words were no longer read): `before`, {symbol: [name, industry]} of the companies
    an earlier stored version of the theme dropped as another business (theme_changes.off_memory), stays out while no words of its own are
    read (`words(symbol)` falsy: nothing shows the earlier finding wrong), with that reason ("before": True); one whose words are read is
    judged on them again, and one they now keep in is no longer held by the earlier finding.
    v55 (R55, the owner's review of the live R54 FMCG deck: Indo National, a battery and torch maker, moved from "Branded packaged foods
    manufacturing" into "Other FMCG companies"): membership is decided before any layer: `scope(symbol)`, {"kind", "said", "text"} when its
    principal business is a kind of product the theme's definition doesn't include (theme_check.off_scope), drops it the same way, with that
    reason ("scope"), from whatever layer or "Other" it was in."""
    from .theme_check import off_industry
    off, seen = [], set()
    before = before or {}
    for v in vc:
        for c in v.get("companies") or []:
            s_ = c.get("ticker")
            if s_ not in todo or s_ in seen:
                continue
            filed = industry_label(c.get('industry')) or 'the theme’s industry'
            if off_industry(evidence(s_)):
                seen.add(s_)
                off.append({"ticker": s_, "name": c.get("name") or s_, "industry": c.get("industry") or "",
                            # c1 (R44, reviewer ask 3): the reason it is out of the theme, kept beside it
                            "why": f"filed under {filed}, its own words describe another business"})
            elif scope is not None and (sc := scope(s_)):
                seen.add(s_)
                where = sc.get("where") or "words"
                off.append({"ticker": s_, "name": c.get("name") or s_, "industry": c.get("industry") or "", "scope": sc["kind"],
                            **({"scope_where": where} if where != "words" else {}),
                            # r67e: the words of its own sentence that name the kind, quoted where the deck names it
                            **({"quote": sc["quote"]} if where == "words" and sc.get("quote") else {}),
                            "why": (f"filed under {filed}; its principal business, in its own words (“{sc['text']}”), is of {sc['kind']} "
                                    f"(“{sc['said']}”), which the theme's definition doesn't include") if where == "words" else
                                   (f"no description of its own is stored; official industry: {sc['text']}, of {sc['kind']} (“{sc['said']}”); "
                                    "outside the theme's definition") if where == "industry" else
                                   (f"filed under {filed}; no description of its own is stored, and its name (“{sc['text']}”) names {sc['kind']} "
                                    f"(“{sc['said']}”); outside the theme's definition")})
            elif s_ in before and words is not None and not words(s_):
                seen.add(s_)
                off.append({"ticker": s_, "name": c.get("name") or s_, "industry": c.get("industry") or "", "before": True,
                            "why": f"filed under {filed}; an earlier version of the theme found its own words describe another business, "
                                   "and no words of its own are read since"})
    if not off:
        return vc, []
    out = [{**v, "companies": [c for c in v.get("companies") or [] if c.get("ticker") not in seen]} for v in vc]
    return [v for v in out if v["companies"] or not v.get("official")], off


REASK_MAX = 60                   # R30: companies of a kept placement whose unknown model is asked again a check, the largest first (gl50: 40 -> 60)
REASK_BATCH = 20                 # gl50: ...in answers of this many each, so one answer is never asked for hundreds of models


def reask_unknown(models: dict, tags: dict, conf, reasked: list, syms: list, about_of, by_sym: dict, evidence, ask, theme: str):
    """R30 (the owner's review of the live R28 Telecom deck: three tower companies left out of "Tower infrastructure" with unknown models): a
    placement kept from before R28 holds "unknown" for companies whose own descriptions are kept now. Those with a description and no model,
    not asked before (`reasked`), are asked once in one answer of at most REASK_MAX (theme_check.recheck_models: a model is kept only when the
    evidence shows it), and every symbol asked is kept in `reasked`, so none is asked twice. Background only (`ask` given). (models, tags,
    confidence, reasked).
    gl50 (R50, the rotating review: "way of earning not shown" for most of a layer, FMCG 37 of 48, Software 9 of 11): the one placement answer
    was asked for the models of up to PLACE_MAX companies and MODEL_MEMBERS of each layer, hundreds in one reply, and gave a fraction; a theme
    whose answer failed had none and nothing asked again. Now every check with the AI asks the companies still without a model, in `syms`'
    order (the caller's: the largest first), in answers of REASK_BATCH, at most REASK_MAX a check, over as many checks as it takes: whatever
    the placement's version (a model asked apart from the placement never moves a company out of the map layer the AI put it in: settled).
    `models` may be None (no answer gave any)."""
    from .theme_check import model_confidence, recheck_models, refine_model
    done = set(reasked)
    want = []
    models = dict(models or {})
    for s_ in dict.fromkeys(x for x in syms if x):
        if s_ in done or (models.get(s_) or "unknown") != "unknown" or not (about_of(s_) or "").strip():
            continue
        want.append(s_)
        if len(want) >= REASK_MAX:
            break
    if not want:
        return models, tags, conf, reasked
    conf, asked_ = dict(conf or {}), []
    for i in range(0, len(want), REASK_BATCH):
        batch = want[i:i + REASK_BATCH]
        try:
            got = recheck_models([{"symbol": s_, "name": (by_sym.get(s_) or {}).get("name") or s_, "was": "unknown", "evidence": evidence(s_)}
                                  for s_ in batch], ask, theme)
        except Exception as e:                   # the AI busy: the rest asked on a later check
            print("theme base: unknown models not asked again:", theme[:40], type(e).__name__, str(e)[:100])
            break
        asked_ += batch
        for s_, md in got.items():
            models[s_] = refine_model(md, evidence(s_))
            conf[s_] = model_confidence(models[s_], evidence(s_), "medium")
    return models, tags, conf, sorted(done | set(asked_))


def stated_for_rest(models: dict | None, conf, syms, evidence) -> tuple[dict | None, dict | None, set]:
    """gl50 (R50): when no answer gave any company a model (the placement's answer failed: the live Biotech and Capital goods maps had none,
    so nothing of R37 ran either, refine_kept running only beside models), each company whose own words state its model in so many words
    takes it ("medium"), by refine_kept's own R37 rule (stated, made exact, kept only where its words show it). Never asks anything.
    (models, confidence, the symbols given one); as given when any model is there already (refine_kept reads those) or none is stated.
    Like R37's, a model only its words state never moves a company out of the map layer it is in (settled)."""
    if models:
        return models, conf, set()
    got, cf = refine_kept({}, {}, evidence, list(dict.fromkeys(x for x in syms if x)))
    add = {s_: m_ for s_, m_ in got.items() if m_ not in ("", "unknown")}
    if not add:
        return models, conf, set()
    return add, {**(conf or {}), **{s_: (cf or {}).get(s_) or "medium" for s_ in add}}, set(add)


def model_names_signature(layers: list[dict]) -> str:
    """Which companies, and which way of earning, each layer the split reshaped holds: its name check is asked again only when this changes."""
    import hashlib
    parts = sorted(f"{v['layer']}:{(v.get('model') or {}).get('id')}:" + ",".join(sorted(c.get("ticker") or "" for c in v["companies"])) for v in layers)
    return hashlib.sha1("|".join(parts).encode(), usedforsecurity=False).hexdigest()[:16]


def renamed_after_split(vc: list[dict], names: set[str], rename: dict) -> list[dict]:
    """The layers with the split's renames (R26) applied to the layers in `names`: the map's name kept as "was", a name another layer has left alone."""
    taken = {v["layer"] for v in vc}
    out = []
    for v in vc:
        r = rename.get(v["layer"]) if v["layer"] in names else None
        if r and r.get("name") and r["name"] not in taken:
            taken.add(r["name"])
            v = {**v, "layer": r["name"], "description": r.get("description") or v.get("description") or "", "was": v.get("was") or v["layer"],
                 "aka": list(dict.fromkeys((v.get("aka") or []) + [v["layer"]]))}          # d53: every name it had (theme_data.same_names)
        out.append(v)
    return out


# ---------- one revenue model a layer (R25) ----------
# The owner's outside review of the R23 decks: "avoid grouping businesses with fundamentally different revenue models just because they
# belong to the same broad theme" (IT services: hardware resellers in "Cloud, AI infrastructure and hardware", an 18-company "Mid-tier digital
# and cloud specialists" catch-all). Each company's model comes with the placement answer (theme_check.place_in_layers, kept with the map).
SPLIT_SHARE = 0.40              # a layer holding more than this share of the theme's placed companies is split...
STORE_SAYS = r"\bstores?\b|\bretailer\b|\bshops?\b|\boutlets?\b"      # d1: a retailer's own words, for one with no model read
INDUSTRY_GROUP_MIN = 5          # d1: companies of one official industry that no map layer's name describes, grouped as a layer of that industry
SPLIT_MIN = 8                   # ...when it has at least this many, by revenue model, else by market value
SPLIT_PART = 3                  # each part of such a split holds at least this many companies


R31_REFINE = ("property_development", "property", "construction", "manufacturing", "fabless", "unknown", "retail",      # models the R31 boundaries can make exact
              "software", "capacity",         # q1: a network operator given software or capacity is telecom_services
              "contract_manufacturing", "platform",     # R36: a chip maker with products of its own is no contract maker; a seller of its own goods is a retailer
              "components",                             # R37: a chip company's packaging and test services are contract making
              "telecom_services")                       # d1: a maker of cables read as an operator makes its own products


def said_for(new, old_model, said) -> str:
    """The confidence an answer gave a company's model, as it counts for the model a rule made of it (q1): the answer's word on a model of
    another family (a telecom operator it called software, at "low") says nothing of the new one, so the rule's model reads its own evidence,
    at most "medium"; else the answer's word as given."""
    from .theme_check import model_family
    if new != old_model and model_family(new) != model_family(old_model) and said == "low":
        return "medium"
    return said


LAYER_MODEL_NOT = (r"\bmaterials?\b|chemicals?|\bgases\b|\bwafers? (?:supplier|maker)|substrates?|"
                   r"(?:semiconductor|wafer fab\w*|capital|process) equipment|electronic design automation|\beda\b")


def models_from_layer(vc: list[dict], models: dict, conf, evidence=None) -> tuple[dict, dict | None]:
    """(models, confidence) with each company of a map layer (not an official group, not "Other") that has no known model given the one
    model its layer's own name states in so many words (theme_check.model_from_words on the name), at "medium" confidence: the map placed it
    there and its own words don't contradict it. Unchanged when the name states no single model (R32). R34: never when the company's own
    evidence states another model, or names materials, chemicals, gases, substrates, equipment or design software (live: a materials maker
    in a fabless layer)."""
    import re
    from .theme_check import MODELS, model_from_words
    given = evidence
    ev_of = given if callable(given) else (lambda s_: (given if isinstance(given, dict) else {}).get(s_))   # the caller passes a reader
    models, out_conf = dict(models), (dict(conf) if isinstance(conf, dict) else {})
    for v in vc:
        if v.get("official") or v.get("by_model"):
            continue
        m_ = model_from_words(str(v.get("layer") or ""))
        if not m_ or m_ not in MODELS:
            continue
        for c in v.get("companies") or []:
            s_ = c.get("ticker")
            if s_ and models.get(s_, "") in ("", "unknown"):
                ev = str(ev_of(s_) or "")
                if model_from_words(ev) not in ("", m_) or re.search(LAYER_MODEL_NOT, ev, re.I):
                    continue
                models[s_] = m_
                out_conf[s_] = "medium"
    return models, (out_conf or conf)


def refine_kept(models: dict, conf, evidence, syms=()) -> tuple[dict, dict | None]:
    """(models, confidence) with the R31/R32 boundaries applied to the models in R31_REFINE (theme_check.refine_model); a company whose model
    changes, or a fabless one of low confidence, has its confidence read again from its evidence, never below what it was (R32: a kept
    placement left 29 of the 37 chip designers out with low confidence). R36: `syms`, the map's companies: one the answer gave no model at
    all is read as "unknown" is (live: Entegris, a chip materials supplier with no model, could sit in whatever layer it was placed in).
    Lane n2 (the outside review of the live R33 decks: TSMC and UMC left out of the foundry layer as "way of earning not shown"): every kept
    model of low confidence has its confidence read again from the evidence as it is now (a 20-F's Item 4 read since): "medium" at most
    when the company's own words show the model, never below what it was."""
    from .theme_check import model_confidence, model_supported, own_words_show, refine_model, stated_model
    models, out_conf = dict(models), (dict(conf) if isinstance(conf, dict) else None)
    absent = [(s_, "unknown") for s_ in dict.fromkeys(x for x in syms if x and x not in models)]
    for s_, md in list(models.items()) + absent:
        new = refine_model(md, evidence(s_)) if md in R31_REFINE else md
        old = (out_conf or {}).get(s_, "")
        stated = False
        if new in ("unknown", ""):
            # R37 (lane r2: 255 of the 1,334 companies of the 14 live maps with no model, most with no words read): one whose own words, read
            # since, state how it earns in so many words takes that model, at "medium" as one the answer didn't give (theme_check.stated_model)
            st = stated_model(evidence(s_))
            exact = refine_model(st, evidence(s_)) if st and model_supported(st, evidence(s_)) else ""
            if exact and (exact == st or model_confidence(exact, evidence(s_), "medium") != "low"):   # made exact into one its words don't show: unknown
                new, old, stated = exact, "medium", True
        if new != md or old == "low":
            models[s_] = new
            if new and new != "unknown":
                out_conf = out_conf if out_conf is not None else {}
                out_conf[s_] = model_confidence(new, evidence(s_), said_for(new, md, old))
                if old == "low" and new == md and own_words_show(new, evidence(s_)):
                    # lane n2: a kept "low" (the AI's word on thinner evidence) gives way to "medium" when the company's own words read since
                    # show the model, never above (the AI's word still caps it: R32)
                    out_conf[s_] = model_confidence(new, evidence(s_), "medium")
                if stated:
                    out_conf[s_] = "medium"          # stated in so many words, never read by the AI: "medium" (R27)
    return models, out_conf


# R37: words of how a company earns, never of what it does: they place no company in a layer (by_model.home_of)
_HOW_STEMS = {_stem(w) for w in ("manufacture", "manufacturer", "manufacturing", "make", "makes", "maker", "makers", "produce", "producer", "production",
              "sell", "sells", "selling", "sold", "sale", "sales", "supply", "supplier", "suppliers", "supplies", "distribution", "distributor",
              "service", "provide", "provider", "earning", "earn", "margin", "revenue", "market", "markets", "marketing", "trade", "trader", "trading",
              "company", "business", "chain", "chains", "store", "stores", "retail", "retailer", "retailers", "shop", "brand", "brands", "customer",
              "customers", "consumer", "consumers", "goods", "items", "range", "leading", "leader", "largest", "large", "small", "global", "group",
              "these", "their", "they", "which", "such", "mainly", "often", "including", "across", "through", "operates", "operator", "engaged",
              "offers", "offering", "focused", "specialty", "specialised", "specialized", "price", "prices", "cost", "costs", "scale", "exposure",
              "depends", "sets", "apart", "them", "from", "have", "with", "that", "this", "other", "unit", "units", "india", "states", "united",
              "headquartered", "incorporated", "limited", "corporation", "holdings", "american", "national", "international")}
STAY = object()
_HALF_RX = re.compile(r" \((?:larger|smaller)\)$")
_KIND_PLAIN = (_PLAIN - {"equipment", "equipments"}) | {"product", "solutions", "systems", "various", "wide"}


def kind_stems(text) -> set[str]:
    """The stems of what a company or a layer's name says is made, sold or done: its words, less those of how any company earns
    (_HOW_STEMS) and the plain words of industry names ("equipment" kept: what a network equipment maker makes)."""
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) >= 3 and w not in _KIND_PLAIN} - _HOW_STEMS


def _short_joined(text) -> str:
    """cl48 (R47): the text in lower case with a compound whose first part is a short word ("off-price", "e-commerce") written as one word,
    as name_says reads it, so "off" of "off-price" is never said by "branched off"."""
    return re.sub(r"\b([a-z0-9]{1,3})-([a-z0-9]+)\b", r"\1\2", str(text or "").lower())


def whole_stems(text) -> set[str]:
    """cl48 (R47): kind_stems with a compound whose first part is a short word read as one word (_short_joined)."""
    return kind_stems(_short_joined(text))


def name_says(name: str, text: str, theme_words: set, description: str = "", by_property: bool = True) -> tuple[bool, bool]:
    """(whether a layer's name states a kind of business beyond the theme's own words, whether a company's own words say it) (d1): a
    hyphenated word of the name is one word ("off-price", never "off" by chance), the others by their stems (kind_stems). r60: or words
    that say the layer's concept (concept_said: "direct-to-home" says "satellite"), by its name or its own `description`."""
    low = str(name or "").lower()
    # a compound whose first part is a short word ("off-price", "e-commerce") is one word; any other compound ("deposit-led") its parts
    joined = [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+", low) if len(w.split("-")[0]) <= 3]
    for w in joined:
        low = low.replace(w, " ")
    rest = kind_stems(low.replace("-", " ")) - theme_words
    if not joined and not rest:
        return False, False
    t = str(text or "").lower()
    # r68e: a property owner's layer is said by the kind of property its words name, never by a word they share ("communities")
    pf = property_fit(name, t) if by_property else None
    if pf is not None:
        return True, pf
    mine = kind_stems(t)
    # a stem of five letters or more says the longer word it starts ("steel" says "steelmaking")
    near = lambda a, b: a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))      # noqa: E731
    said = any(re.search(r"\b" + r"[- ]?".join(map(re.escape, w.split("-"))) + r"\b", t) for w in joined) or any(near(a, b) for a in mine for b in rest)
    return True, said or bool(concept_said(name, t, description, by_property))


FILING_TITLES = "From its own filings:"


def own_text(evidence) -> str:
    """A company's own words in its evidence, its official industry line left out. cv47 (R46, the live Release 46 Utilities deck: the cable
    and electrical equipment makers' layers never formed on live): the titles of its filings ("From its own filings: Board meeting...",
    theme_routes.own_filings) are no words of its own about its work (no_words), so they are left out too: their "own" said the name
    "Makers of their own products", and "Order or contract" would say "contracts"."""
    t = str(evidence or "")
    m = re.match(r"\s*Industry:\s*[^.]*\.\s*", t)
    t = t[m.end():] if m else t
    i = t.find(FILING_TITLES)
    return t[:i].rstrip() if i >= 0 else t


def layer_says(v: dict, text: str, theme_words: set) -> tuple[bool, bool]:
    """cl48 (R47): name_says over a layer's names, the map's own ("was") and the one shown (a half's "(larger)" left out): (whether either
    states a kind of business beyond the theme's words, whether the company's own words say what either says)."""
    got = [name_says(n, text, theme_words, v.get("description") or "") for n in dict.fromkeys(x for x in (v.get("was"), _HALF_RX.sub("", v.get("layer") or "")) if x)]
    return any(g[0] for g in got), any(g[1] for g in got)


# r58 (R58, the owner's review of the live R57.2 Regional banks deck: national money-centre banks and small community banks in one layer,
# "Large national banks and small community banks", halved by count, so a $700 bn bank and a $3 bn one were one comparison): a layer whose
# name joins a large scale and a small one is split by scale, into bands of market value relative to its largest member, each named
MIXED_SCALE = re.compile(r"\b(?:large|national|money[- ]cent(?:er|re)|big)\b.*\band\b.*\b(?:small|community|local)\b", re.I)
BAND_TOP = 0.10                 # a member worth this share of the layer's largest or more is of its large scale
BAND_LOW = 0.01                 # ...below this share, of its small scale; between them, mid-sized


def scale_bands(vc: list[dict]) -> list[dict]:
    """r58: each named layer whose name joins a large and a small scale (MIXED_SCALE) with 2 * SPLIT_PART companies or more split into its
    large, mid-sized and small members by market value relative to its largest (BAND_TOP, BAND_LOW), named from its own name's two parts
    ("Large national banks", "Mid-sized banks", "Small community banks"). A band of fewer than SPLIT_PART companies joins the next one."""
    out = []
    for v in vc:
        name = _HALF_RX.sub("", v.get("layer") or "")
        cos = v.get("companies") or []
        if v.get("official") or v.get("scale") or not MIXED_SCALE.search(name) or len(cos) < 2 * SPLIT_PART:
            out.append(v)
            continue
        big_part, _, small_part = name.partition(" and ")
        noun = (re.findall(r"[A-Za-z]+", small_part) or ["companies"])[-1]
        top = max((c.get("cap") or 0) for c in cos)
        if top <= 0 or not small_part:
            out.append(v)
            continue
        bands = {"large": [], "mid": [], "small": []}
        for c in sorted(cos, key=lambda c: (-(c.get("cap") or 0), c.get("ticker") or "")):
            r_ = (c.get("cap") or 0) / top
            bands["large" if r_ >= BAND_TOP else "small" if r_ < BAND_LOW else "mid"].append(c)
        if len(bands["large"]) < SPLIT_PART:
            bands["mid"] = bands["large"] + bands["mid"]
            bands["large"] = []
        if len(bands["small"]) < SPLIT_PART:
            bands["mid"] += bands["small"]
            bands["small"] = []
        if len(bands["mid"]) < SPLIT_PART and bands["mid"]:
            (bands["large"] if bands["large"] else bands["small"]).extend(bands["mid"])
            bands["mid"] = []
        named = {"large": big_part.strip(), "mid": f"Mid-sized {noun.lower()}", "small": small_part.strip()[:1].upper() + small_part.strip()[1:]}
        made = [(k, cs) for k, cs in bands.items() if cs]
        if len(made) < 2:
            out.append(v)
            continue
        for k, cs in made:
            why = (f"“{name}” split by scale, as one comparison would join its largest and smallest: "
                   + ("worth a tenth of its largest member or more" if k == "large" else "worth under a hundredth of its largest member"
                      if k == "small" else "worth between a hundredth and a tenth of its largest member") + ", by market value")
            cs = [c if isinstance(c.get("refit"), dict) else {**c, "refit": {"from": name, "to": named[k], "why": why}} for c in cs]
            out.append({**v, "layer": named[k], "description": "", "companies": cs, "band": k, "band_why": why,
                        "aka": list(dict.fromkeys(list(v.get("aka") or []) + [name]))})
    return out


def _model_layer(name: str, cos: list[dict], **kw) -> dict:
    return {"layer": name, "description": "", "by_model": True, "companies": cos, **kw}


# R40: families whose companies one layer of a single official industry counts together (making its own products, or parts and components)
KIN_FAMILIES = (frozenset({"making", "components"}),)


def held_to_previous(vc: list[dict], previous: dict, about_of) -> list[dict]:
    """R45 (lane tx2; the live Release 45 Automotive deck, built while the map's picks were being checked again under the new rules: a
    tractor maker the check had moved out of "Commercial and three-wheeler vehicle makers" on the live Release 43 was back in it, unchecked):
    a company in a layer of the map that is not checked yet (the map's own pick, its words not yet checked for that layer) whose previous
    live layer (`previous`: {symbol: the map's name of that layer}, map_names_of) is another layer of the map keeps that previous layer,
    unless it has evidence of the one it is in: its own words say what that layer's name says, or that layer holds a larger share of its
    official industry. A company checked since ("verified") or placed after the map is never held."""
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    name = lambda v: v.get("was") or _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    by_name = {}
    for v in own:
        by_name.setdefault(name(v), v)
    inds = {id(v): [key(c.get("industry")) for c in v.get("companies") or [] if c.get("industry")] for v in own}
    share = lambda v, ind: inds[id(v)].count(ind) / max(1, len(v.get("companies") or []))      # noqa: E731
    moves = []
    for v in own:
        for c in v.get("companies") or []:
            s_ = c.get("ticker")
            to = by_name.get(previous.get(s_) or "")
            if to is None or to is v or name(to) == name(v) or c.get("verified") is not False or c.get("placed"):
                continue
            ind = key(c.get("industry")) if c.get("industry") else ""
            words = own_text(about_of(s_) or c.get("what") or "")
            if name_says(name(v), words, set())[1] or (ind and share(v, ind) > share(to, ind)):
                continue
            moves.append((v, c, to))
    if not moves:
        return vc
    copies = {id(v): {**v, "companies": list(v.get("companies") or [])} for v in own}
    for v, c, to in moves:
        copies[id(v)]["companies"] = [x for x in copies[id(v)]["companies"] if x is not c]
        copies[id(to)]["companies"].append({**c, "held": "previous"})
    return [copies.get(id(v), v) for v in vc]


def map_names_of(previous: dict | None, kept: dict | None) -> dict:
    """R45 (lane tx2): {symbol: the map's own name of its previous live layer}: a shown name the kept answer gave a map layer (its "rename",
    or the split's "model_names") read back as that layer's own name, a half of a layer split by market value as the layer."""
    if not previous:
        return {}
    back: dict = {}
    for ren in ((kept or {}).get("rename"), ((kept or {}).get("model_names") or {}).get("rename")):
        for k, x in (ren or {}).items() if isinstance(ren, dict) else ():
            if isinstance(x, dict) and x.get("name"):
                back.setdefault(str(x["name"]), str(k))
    return {s_: back.get(_HALF_RX.sub("", str(n)), _HALF_RX.sub("", str(n))) for s_, n in previous.items() if s_ and n}


# gl52: a second way of earning a layer's own name can state, in so many words, beside how most of its companies earn
OF_LAYER_WORDS = 3          # x57: words of what it makes or does (kind_stems) a description needs for its official industry to place it in a layer's figures beside a low read
NAME_PART_MODEL = {"construction": r"\bepc\b|engineering,? procurement,? (?:and|&) construction",
                   # x57 (RC4: Inox Green, "wind power operation and maintenance ("O&M") service providers", left out of "Wind turbine
                   # manufacturing and servicing" as read only weakly): a layer whose name states servicing takes a servicer whose words say so
                   "managed_services": r"\bservicing\b|\boperations? (?:and|&) maintenance\b|\bo ?& ?m\b",
                   # r64e (the live R63 US Steel and metals deck: Reliance and Ryerson, the map's own "Metals service centers", left out of
                   # "Metals distributors and mining developers" as a different revenue model once miners placed by their words outnumbered
                   # them): a layer whose name states distributors or service centers takes a distributor whose words say so ("distribution"
                   # alone is no name part: a power grid's transmission and distribution is no resale)
                   "distribution": r"\bdistribut(?:ors?|es?|ing)\b|\bwholesal(?:e|ers?|ing)\b|\bservice cent(?:er|re)s?\b"}
# gl52 (the integrator): a company with no words of its own counts on its industry in a layer only when that layer holds at least this share,
# and this many, of the theme's companies of that industry that were read or placed by the AI (by_model industry_points_here); two in three:
# at 60% the live Capital goods "Industrial Products" (25 of its 40 read companies in "Engines and industrial machinery makers", 62.5%, the
# other 15 over six layers) still counted
ON_INDUSTRY_SHARE, ON_INDUSTRY_MIN = 2 / 3, 3
TOP_SHARE = 4                   # r572: ...and never more than the theme's largest quarter
TOP_MEMBERS = 10                # r572: the theme's largest companies by market value, never left out of their layer's figures on insufficient evidence alone
MODEL_LINE_MIN = 3              # gl52: companies a sparse layer's way of earning must be shown for before its line names it


def by_model(vc: list[dict], models: dict, theme: str = "", tags: dict | None = None, confidence: dict | None = None,
             evidence_of=None, settled=(), previous: dict | None = None, moved_before: dict | None = None, about_of=None,
             published: dict | None = None) -> list[dict]:
    """The placed map's layers with one revenue model family each, from `models` ({symbol: model id}, theme_check.MODELS):
    1. a layer of the map whose companies earn in different ways keeps its main family (the most of its companies; a tie, the family of the first
       of them, the map's own pick); each other company moves to the layer whose main family is its own (the largest), else to a new layer named
       by that model ("Hardware resale and integration"). A company of the "Other" group whose model is known goes the same way, so "Other" keeps
       only companies the evidence can't place. A company with no known model stays where it is; so does one whose model is of "low"
       confidence (R27, `confidence`: {symbol: high/medium/low}), which counts as unknown.
    2. a layer above SPLIT_SHARE of the placed companies (and SPLIT_MIN or more) is split by its models when two or more hold SPLIT_PART
       companies each, else into its larger and smaller halves by market value.
    3. (R27) a split never leaves a layer of one company: a layer the split made or reshaped that holds one company gives it to the largest layer
       of its family, else to the theme's "Other" group, and is not a layer of its own. R39: the company of a layer the split made joins only
       a layer of its family whose words it shares (`fits`), else "Other".
    3b. (R31) one primary model a layer: a layer the split made whose primary model, family and sub-basis (theme_check.sub_basis: a metals
       family's commodity) are those of one of the map's own layers joins it. R32: so does any layer named by how it earns (a model's or a
       family's own name, "Product designers that outsource making"), and two such layers become one; it joins the largest layer of the same
       key named by what it makes or serves when there is one such layer (R36: with two or more, which of them a company belongs to isn't
       shown by how it earns, so the model-named layers become one layer of their own), else the largest of them. R39 (lane s1-fit: the live
       R37 Semiconductors deck had Micron, Intel and SK Hynix, lasers and LED makers in "Semiconductor equipment"): a model-named layer joins a
       layer named by what it makes or serves only with the companies the split moved there whose own words share two of the words that
       layer's name and description say is made or done (`fits`; the theme's own name left out); companies the map placed together keep
       joining as before; the others keep their layer (one left alone goes to "Other").
       Two of the map's own layers named by what they make or serve that share
       them both stay (two-wheelers and cars both make their own products), and each one's line says so (`same_as`).
    4. every layer of the map carries `model`: {"id", "family", "line", "known", "of", "out", "also"}, the one line the deck shows of what its
       companies have in common; R27: the companies whose model is unknown or of low confidence are listed but marked `model_out` (left out of
       the layer's figures and rankings; the line says how many and why), and the line names the commonest secondary way of earning of its
       companies ("3 of the 9 also earn from ..."; `tags`: {symbol: [model ids]}), so no company is shown as earning one way only.
    Every company carries "model", "model_tags" and "model_confidence" (R27, for the deck's checks). Facts only: the models are the companies'
    own evidence as the AI read it.
    R45 (lane tx2): `previous` ({symbol: the map's name of its layer in the previous live placement}, map_names_of): a company leaving the
    layer it was in there for another layer (a layer of the map or one the split names by how it earns) moves only on evidence of that layer
    (evidence_for: its own words say the layer's name, or the layer holds a larger share of its official industry); else it keeps its layer,
    listed but left out of the layer's figures as another way of earning. Moving to "Other" (no layer fits) is not held back."""
    from collections import Counter

    from .theme_check import (FAMILIES, MODELS, SUB_BASIS, SUB_JOIN, SUB_OF, model_evidence, model_family, name_models, off_industry, own_goods,
                              principal_words, secondary_models, words_models,
                              stated_model, sub_basis)
    tags, conf = tags or {}, dict(confidence or {})          # d1: a copy (the industry group sets models its members state)
    every = {s: m_ for s, m_ in (models or {}).items() if m_ in MODELS}
    # gl52 (R52): a model its official industry contradicts outright (a medical laboratory read as managed IT services at low confidence, or as
    # consumer services) gives way to the one the industry states, at "medium" (stated by its industry, not its own words)
    if evidence_of is not None:
        from .theme_check import industry_model
        for s_ in list(every):
            try:
                ev_s = evidence_of(s_) or ""
            except Exception:
                ev_s = ""
            md_ = industry_model(every[s_], ev_s, conf.get(s_, ""))
            if md_ != every[s_]:
                every[s_], conf[s_] = md_, "medium"
    models = {s: m_ for s, m_ in every.items() if conf.get(s) != "low"}
    out = [dict(v, companies=list(v.get("companies") or [])) for v in vc]
    ev_memo: dict = {}

    def ev(c):
        s_ = c.get("ticker")
        if s_ not in ev_memo:
            got = ""
            if evidence_of is not None:
                try:
                    got = evidence_of(s_) or ""
                except Exception as e:          # the evidence store can't answer now: the company's own line and industry still count
                    print("theme base: evidence not read:", s_, type(e).__name__, str(e)[:100])
            ev_memo[s_] = got or model_evidence(c.get("industry") or "", c.get("what") or "")
        return ev_memo[s_]
    # R36 (GPT review of the live R35 Semiconductors deck: solar tracker and module makers, filed as semiconductors, among "Makers of their own
    # products"): a company whose own words show another business than the one its official industry files it under (theme_check.off_industry)
    # moves to no layer by how it earns: the "Other" group keeps it, and in a layer of the map it is left out of the figures as another business
    outside = {c.get("ticker") for v in out for c in v["companies"] if c.get("ticker") in models and off_industry(ev(c))}
    models = {s: m_ for s, m_ in models.items() if s not in outside}
    another, read = set(outside), dict(models)          # R40: the companies of another business, and every model as read (step 4)
    own = [v for v in out if not v.get("official")]
    if not own or not every:
        return vc
    fam = lambda c: model_family(models.get(c.get("ticker")))       # noqa: E731
    before = {id(v): {c.get("ticker") for c in v["companies"]} for v in own}
    # c54: where each company was before the split by how companies earn (a layer's map name, or "" for "Other"), for the sold-what test
    placed_in = {c.get("ticker"): v.get("was") or _HALF_RX.sub("", v.get("layer") or "") for v in own for c in v["companies"]}

    # r572 (R57.2, the live R57.1 Restaurants deck: "Franchisors and brand licensors", its name stating franchising, was read as licensing,
    # the one company of it read at medium or high confidence being a licensor, and McDonald's, Yum and Restaurant Brands, each read as a
    # franchisor at low confidence, were left out as "insufficient evidence"): in a layer of the map whose own name states one way of earning,
    # where most of its companies are read that way, a company so read at low confidence whose principal words name no other way counts as
    # read that way (its row says it was read at low confidence: "read_low")
    named_low: set = set()
    for v in own:
        fn_ = {model_family(m_) for m_ in name_models(_HALF_RX.sub("", v.get("layer") or "")) | name_models(v.get("was") or "")} - {""}
        if len(fn_) != 1:
            continue
        fn_ = fn_.pop()
        agree_ = [c for c in v["companies"] if model_family(every.get(c.get("ticker")) or "") == fn_ and c.get("ticker") not in outside]
        if len(agree_) * 2 <= len(v["companies"]):
            continue
        up_ = {c.get("ticker") for c in agree_ if c.get("ticker") not in models
               and all(model_family(x) in ("", fn_, "holding") for x in words_models(principal_words(ev(c))))}
        known_ = Counter(model_family(models[c.get("ticker")]) for c in v["companies"] if c.get("ticker") in models)
        # only where the layer's way becomes its main one: the companies read so outnumber every other way read at medium or high
        # (and only where its main way read at medium or high confidence is another: a layer already read its named way is left as it is)
        if known_ and known_.most_common(1)[0][0] != fn_ and len(up_) + known_.get(fn_, 0) > max((n for f_, n in known_.items() if f_ != fn_), default=0):
            for s_ in up_:
                models[s_] = every[s_]
            named_low |= up_

    def main(cos):
        counts = Counter(fam(c) for c in cos if fam(c))
        if not counts:
            return ""
        top = max(counts.values())
        return next(fam(c) for c in cos if fam(c) and counts[fam(c)] == top)

    def name_of(cos, f):
        fines = {models[c["ticker"]] for c in cos if c.get("ticker") in models and fam(c) == f}
        return MODELS[next(iter(fines))][1] if len(fines) == 1 else FAMILIES.get(f, (MODELS[sorted(fines)[0]][1],))[0]

    # 1. one family a layer; "Other" keeps only what the evidence can't place
    mains, movers = {}, []
    for v in own:
        f = mains[id(v)] = main(v["companies"])
        if f:
            # R37 (lane r2): a company the map placed in a layer whose model only its own words state (`settled`: no answer gave it one) is never
            # moved by it: it stays in the map's layer, left out of its figures as a company of another way of earning
            held = {c.get("ticker") for c in v["companies"] if fam(c) not in ("", f) and c.get("ticker") in settled}
            outside |= held
            for s_ in held:
                models.pop(s_, None)
            movers += [{**c, "_from_layer": id(v)} for c in v["companies"] if fam(c) not in ("", f) and c.get("ticker") not in held]
            v["companies"] = [c for c in v["companies"] if fam(c) in ("", f) or c.get("ticker") in held]
    for v in out:
        if v.get("official") and v.get("basis") == "rest":
            movers += [{**c, "fit": True} for c in v["companies"] if fam(c)]
            v["companies"] = [c for c in v["companies"] if not fam(c)]
    home, homes = {}, {}
    for v in own:
        f = mains[id(v)]
        if f and (f not in home or len(v["companies"]) > len(home[f]["companies"])):
            home[f] = v
        if f:
            homes.setdefault(f, []).append(v)
    new: dict[str, dict] = {}

    inds = {id(v): Counter(key(x.get("industry")) for x in v["companies"] if x.get("industry")) for v in own}     # before any company moves
    sizes = {id(v): len(v["companies"]) for v in own}
    kinds = {id(v): sub_basis(mains[id(v)], [ev(x) for x in v["companies"] if fam(x) == mains[id(v)]]) for v in own
             if mains.get(id(v)) in SUB_JOIN}
    stays = []
    theme_words = kind_stems(theme)

    def fits(c, v) -> bool:
        """R39 (lane s1-fit): a company's own words share two of the words of what a layer's name and description say is made or done (the
        theme's own name left out: "Semiconductor" in "Semiconductor equipment" says nothing of which layer), never one by chance."""
        return len(kind_stems(own_text(ev(c))) & (kind_stems(f"{v.get('layer') or ''} {v.get('description') or ''}") - theme_words)) >= 2

    def evidence_for(c, t, src, ind) -> bool:
        """R45 (lane tx2): whether a company has evidence for layer `t` over the layer `src` it is in: its own words say what t's name says
        (name_says), or t holds a larger share of its official industry `ind` than src (both counted before any company moves)."""
        if name_says(t.get("was") or _HALF_RX.sub("", t.get("layer") or ""), own_text(ev(c)), theme_words)[1]:
            return True
        share = lambda v: inds.get(id(v), Counter())[ind] / max(1, sizes.get(id(v), 0))      # noqa: E731
        return bool(ind) and share(t) > share(src)

    def home_of(c, f):
        """The map's layer of its family a company moving by how it earns goes to: the largest of them. R36 (the live R35 Consumer retail
        deck: Amazon, leaving the marketplaces, would go to "Apparel and fashion retail chains"): for a company leaving a layer the map placed it
        in, not the largest when that holds no company of its own official industry and another is mostly of it.
        R37 (lane r2), for a company of the "Other" group only (the same deck: two propane distributors, two pawnbrokers and three online
        sellers moved out of "Other" into "Apparel and fashion retail chains"): the largest stands when it holds the company's official
        industry, or its name or description shares a word of what the company's own words say it does (none of how any company earns:
        makes, sells, supplies...), or the company has no words; else the layer whose every company is of its official industry and whose
        name or description shares such a word, unless the layer's name states another way of earning ("Custom synthesis manufacturers"); else,
        when no layer of its family holds its industry or shares its words, it stays in "Other" (the map has no layer of its business).
        R39 (lane s1-fit): a company with no words of its own joins the largest only when that layer holds its industry (or no industry is
        known), else stays in "Other" (also when leaving a map layer with no layer mostly of its industry). First, when the largest holds none of its industry and a layer of the map is all of its industry (and most of the
        map's companies of it), that layer, of whatever way of earning (left out of its figures); and where the largest neither holds its
        industry nor shares its words and no layer of its family holds its industry, never the largest: the layer of its family sharing
        two of its words (not one named for another way of earning), else "Other". Everything else as R37.
        A contract maker's kind (packaging and test, or a foundry: theme_check.contract_kind) joins only a contract layer of its kind, else
        a layer of its own (R37: foundries beside packaging and test services under "Packaging, test and materials suppliers")."""
        big = home.get(f)
        if big is None:
            return None
        cands = homes.get(f) or [big]
        if f in SUB_JOIN:
            kind = SUB_OF[SUB_BASIS[f]](ev(c))
            if kinds.get(id(big)) not in ("", kind):
                alike = [v for v in cands if kinds.get(id(v)) == kind]
                return max(alike, key=lambda v: sizes.get(id(v), 0)) if alike else None
        ind = key(c.get("industry")) if c.get("industry") else ""
        same = lambda v: inds.get(id(v), Counter())[ind] if ind else 0      # noqa: E731
        if c.get("_from_layer"):
            src = next((v for v in own if id(v) == c["_from_layer"]), None)
            mine = kind_stems(own_text(ev(c)))
            if not ind or same(big):
                return big
            mostly = [v for v in cands if same(v) * 2 > sizes.get(id(v), len(v["companies"]))]
            if mostly:
                t = max(mostly, key=lambda v: sizes.get(id(v), 0))
                # R45 (lane tx2, the outside review of the live Release 45 Automotive deck: Bosch and Asahi India Glass, in the component
                # suppliers' layer the map placed them in, went to "Batteries and tractor makers" once that layer, having lost a tractor
                # maker, was two of three of their industry): a company leaves a map layer mostly of its industry for another layer of
                # its industry only on evidence of that layer: its own words say what the layer's name says, or the layer holds a larger
                # share of its industry; else it stays, listed but left out of the layer's figures as another way of earning
                if src is not None and same(src) * 2 > sizes.get(id(src), 0) and not evidence_for(c, t, src, ind):
                    return src
                return t
            # R41 (lane s2-exact, the live Release 38.1 Automotive deck: Bosch and Asahi India Glass, in the component suppliers' layer the
            # map placed them in, read as makers of their own products, went to "Tyre manufacturers", the largest makers' layer, which holds
            # none of their industry): when no layer of its family is mostly of its industry and the map layer it is in is, it stays there,
            # listed but left out of the layer's figures as another way of earning; not when the largest's own name says what its words say
            if src is not None and same(src) * 2 > sizes.get(id(src), 0) and not mine & (kind_stems(big.get("layer") or "") - theme_words):
                return src
            # R39 (lane s1-fit): no words of its own and the largest holds none of its industry: nothing places it there ("Other")
            if not mine:
                return STAY
            # cl48 (R47, the outside review of the live Release 46 Consumer retail deck: a designer of branded athletic apparel the map
            # placed with the brand owners, read as a retailer, went to "Off-price and dollar stores", the largest of the retailers' layers,
            # which holds none of its industry): the largest takes it by default only when its own words say what that layer's name says
            # or the name states no kind of business; else its own words decide: the map's layer it is in when they say that layer's
            # name (listed there, left out of its figures as another way of earning), else the layer of its family that shares two of
            # their words, one of them in its name (never one by chance: "homes" never says "Home improvement"), else "Other"
            named_, says_ = layer_says(big, own_text(ev(c)), theme_words)
            if not named_ or says_:
                return big
            if src is not None and layer_says(src, own_text(ev(c)), theme_words)[1]:
                return src
            said_ = whole_stems(own_text(ev(c)))
            told = [v for v in cands if v is not big and stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))
                    and len(said_ & whole_stems(f"{v.get('layer') or ''} {v.get('description') or ''}")) >= 2
                    and said_ & (whole_stems(v.get("layer") or "") - theme_words)]
            return max(told, key=lambda v: (len(said_ & whole_stems(f"{v.get('layer') or ''} {v.get('description') or ''}")), sizes.get(id(v), 0))) \
                if told else STAY
        # R39 (lane s1-fit; the live R37 Automotive deck: Bosch and Asahi India Glass, auto component makers the answer read as makers of their
        # own products, moved into "Tyre manufacturers"): when the largest layer of its family holds none of its industry and a layer of the
        # map is all of its industry and holds most of the map's companies of it, that layer, whatever way its companies earn; it is listed
        # there but left out of the layer's figures and split as another way of earning. Not when the largest's own name says what its words
        # say ("Network equipment makers" for a telecom equipment maker)
        mine = kind_stems(own_text(ev(c)))
        spread = sum(same(v) for v in own)
        kin = [v for v in own if v not in cands and sizes.get(id(v)) and same(v) == sizes[id(v)] and same(v) * 2 > spread
               and stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))] \
            if ind and not same(big) and not mine & (kind_stems(big.get("layer") or "") - theme_words) else []
        if kin:
            return max(kin, key=lambda v: same(v))
        words = lambda v: kind_stems(f"{v.get('layer') or ''} {v.get('description') or ''}")      # noqa: E731
        # R39 (lane s1-fit; live R37 Consumer retail: a propane distributor and a pawnbroker whose stored evidence held no words of their
        # own went to "Off-price", the largest, which holds none of their industry): a company with no words joins the largest only when
        # that layer holds its official industry (no industry known either: the largest, as before); else it stays in "Other"
        if not mine:
            return big if (same(big) or not ind) else STAY
        # d1 (the outside review of the live Release 41 Consumer retail deck: Dillard's, Gap, Urban Outfitters, Abercrombie, Macy's and Kohl's
        # in "Off-price, dollar and discount store chains", the largest of the retailers' layers, by their industry alone, while American Eagle
        # and Buckle, as like them, sat in "Other"): when the largest's own name states a kind of business (its words apart from the theme's:
        # off-price, dollar, discount) that the company's own words don't say, holding its industry doesn't place it there: the layer of its
        # family whose name its words do say, else "Other"
        # off-price, dollar, discount) that the company's own words don't say, and the largest is no catch-all of its family (it holds under
        # half of the family's companies), and its words share none of that layer's, holding its industry doesn't place it there: "Other" (an
        # online seller still joins the layer whose name states both ways of earning: R40 below)
        named_, says_ = name_says(big.get("layer") or "", own_text(ev(c)), theme_words)
        # cl48 (R47): "off-price" in the layer's words is one word, never shared by a company's "branched off" by chance (whole_stems)
        narrow = named_ and not says_ and not whole_stems(own_text(ev(c))) & whole_stems(f"{big.get('layer') or ''} {big.get('description') or ''}") \
            and sizes.get(id(big), 0) * 2 <= sum(sizes.get(id(v), 0) for v in cands)
        if narrow:
            c["_narrow"] = True
        if (same(big) or mine & words(big)) and not narrow:
            return big
        alike = [v for v in cands if sizes.get(id(v)) and same(v) == sizes[id(v)] and mine & words(v)
                 and stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))]
        if alike:
            return max(alike, key=lambda v: sizes[id(v)])
        if ind and not any(same(v) or mine & words(v) for v in cands):
            return STAY
        # R39 (lane s1-fit; the live R37 Consumer retail deck had 34 such companies in "Off-price, dollar and value-format retailers", the
        # largest, because some other layer shared one of their words): the largest neither holds its industry nor shares its words, and no
        # layer of its family holds its industry (where one does, the map groups its industry there and the largest stands, as before): the
        # layer of its family sharing two of its words, never one whose name states another way of earning, never a new layer; else "Other".
        # R41 (lane s2-exact, the live Release 38.1 Consumer retail deck: Chewy and eleven more online sellers, two pawnbrokers and a propane
        # distributor in "Off-price, dollar and discount store chains", the largest, which holds none of their industry, because "Online
        # retailers and marketplaces", a layer whose name states another way of earning, held some of it): a layer whose name states another
        # way of earning, which never takes the company, doesn't count as the map's layer of its industry; then the largest stands only as the
        # family's catch-all (it holds most of the companies of the family's layers), and the layer sharing two of its words shares one of
        # its name (live: Lulus, sharing "beautiful" and "matter" with the prose of "Home improvement and specialty chains", stays in "Other")
        fair_name = lambda v: stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))      # noqa: E731
        holds = [v for v in cands if same(v)]
        # R40 (the owner's review of the live Release 39 Consumer retail deck: Chewy, Revolve, Stitch Fix and more online sellers in "Other"
        # beside "Online retailers and marketplaces", whose map name "Online marketplaces" states a platform's way of earning): a layer whose
        # shown name states two ways of earning, the company's one of them, takes it when it holds its industry and the company's own words
        # say what its name says (share a word of it; "e-commerce" says "online") or fit it (two words of its name and description)
        said = mine | ({_stem("online")} if re.search(r"\be-?commerce\b", own_text(ev(c)), re.I) else set())
        both = [v for v in holds if v is not big and len(name_models(v.get("layer"))) >= 2 and models.get(c.get("ticker")) in name_models(v.get("layer"))
                and (said & (kind_stems(v.get("layer") or "") - theme_words) or fits(c, v))]
        if both:
            return max(both, key=lambda v: (same(v), sizes.get(id(v), 0)))
        # d1: one the largest's name doesn't describe goes to the layer of its family it fits (below), else "Other" (with the like of it of
        # its industry, a layer of that industry: by_model below)
        if not narrow and (not ind or any(fair_name(v) for v in holds) or (holds and sizes.get(id(big), 0) * 2 > sum(sizes.get(id(v), 0) for v in cands))):
            return big
        fair = [v for v in cands if v is not big and fair_name(v)]
        two = [v for v in fair if len(mine & words(v)) >= 2 and mine & (kind_stems(v.get("layer") or "") - theme_words)
               and not (narrow and v is big)]
        return max(two, key=lambda v: (len(mine & words(v)), sizes.get(id(v), 0))) if two else STAY
    # d1 (the outside review of the live Release 41 decks: Fortinet, the map's own pick for "Network security appliances and subscriptions",
    # and Arm, its pick for "Design software and IP licensing", left them by how they earn for "Other", the map having no layer of their
    # way of earning): a company the map itself named in a layer (never one placed after it) whose way of earning no layer of the map has,
    # and no other company leaving a layer shares, and whose own words say what that layer's name says, stays in the map's layer, listed
    # but left out of its figures as another way of earning
    lone_fam = Counter(fam(c) for c in movers if home.get(fam(c)) is None)
    for c in movers:
        f = fam(c)
        if home.get(f) is None and lone_fam[f] == 1 and c.get("_from_layer") and not c.get("placed"):
            src_ = next((v for v in own if id(v) == c["_from_layer"]), None)
            # and only where its own words say what the layer's name says (a materials supplier in "Chip equipment" never stays: lane m1)
            if src_ is not None and name_says(src_.get("was") or src_.get("layer") or "", own_text(ev(c)), theme_words)[1]:
                outside.add(c.get("ticker"))
                models.pop(c.get("ticker"), None)
                src_["companies"].append({k: x for k, x in c.items() if k != "_from_layer"})
                continue
        target = home_of(c, f)
        src_ = next((v for v in own if id(v) == c.get("_from_layer")), None) if previous else None
        if src_ is not None and target is not STAY and target is not src_ and previous.get(c.get("ticker")) in (
                _HALF_RX.sub("", src_.get("layer") or ""), src_.get("was")) \
                and not evidence_for(c, target or {"layer": name_of([c], f)}, src_, key(c.get("industry")) if c.get("industry") else ""):
            target = src_            # R45: kept in its previous live layer, no evidence for the new one
        if target is STAY:
            stays.append({k: x for k, x in c.items() if k not in ("_from_layer", "fit")})
            continue
        c.pop("_narrow", None)
        if target is not None and mains.get(id(target)) != f:      # R39: in the layer of its industry, another way of earning
            outside.add(c.get("ticker"))
            models.pop(c.get("ticker"), None)
        stayed = target is not None and id(target) == c.get("_from_layer")       # R41: kept in the map's layer of its industry
        target = target or new.setdefault(f, _model_layer("", []))
        target["companies"].append({**{k: x for k, x in c.items() if k != "_from_layer"}, **({} if stayed else {"moved": True})})
    if stays:
        rest_v = next((v for v in out if v.get("official") and v.get("basis") == "rest"), None)
        if rest_v is not None:
            rest_v["companies"] = sorted(rest_v["companies"] + stays, key=lambda c: (-(c.get("cap") or 0), c.get("ticker") or ""))
            # d1: the companies the largest layer's name doesn't describe (above) and the companies of "Other" of the same official industry
            # whose words say no other way of earning become a layer of that industry when they are INDUSTRY_GROUP_MIN or more (the live
            # Release 41 Consumer retail deck: Gap, Abercrombie, Urban Outfitters beside American Eagle and Buckle, all family clothing chains)
            from .theme_check import OWN_SAYS
            for ind_k in sorted({key(c.get("industry")) for c in stays if c.get("_narrow") and c.get("industry")}):
                lead = [c for c in stays if c.get("_narrow") and key(c.get("industry")) == ind_k]
                f_ = fam(lead[0])
                if re.search(r"\b(?:misc\w*|other|diversified|nec|general)\b", industry_label(lead[0].get("industry") or ""), re.I):
                    continue          # an industry that names no one kind of business ("Miscellaneous retail") makes no layer
                says = "|".join([STORE_SAYS] * (f_ == model_family("retail")) + [OWN_SAYS[m_] for m_ in OWN_SAYS if model_family(m_) == f_])
                # with them, a company of "Other" of that industry whose model is unknown only when its own words state the family's way
                # of earning ("a clothing retailer ... 451 stores")
                lead_m = {models.get(c.get("ticker")) for c in lead}
                grp = [c for c in rest_v["companies"] if key(c.get("industry")) == ind_k
                       and (models.get(c.get("ticker")) in lead_m or (not fam(c) and says and re.search(says, own_text(ev(c)), re.I)))]
                if len(lead) >= SPLIT_PART and len(grp) >= INDUSTRY_GROUP_MIN:
                    ids = {id(c) for c in grp}
                    top_m = Counter(models.get(c.get("ticker")) for c in lead).most_common(1)[0][0]
                    for c in grp:            # one whose model no answer gave takes the one its own words state ("a clothing retailer")
                        if not fam(c) and c.get("ticker"):
                            models[c["ticker"]] = every[c["ticker"]] = top_m
                            conf[c["ticker"]] = "medium"
                    rest_v["companies"] = [c for c in rest_v["companies"] if id(c) not in ids]
                    label = industry_label(grp[0].get("industry") or "")
                    out.insert(next((i for i, v in enumerate(out) if v.get("official")), len(out)),
                               {"layer": label, "description": "", "industry_group": True,
                                "companies": [{k: x for k, x in c.items() if k != "_narrow"} for c in grp]})
            rest_v["companies"] = [{k: x for k, x in c.items() if k != "_narrow"} for c in rest_v["companies"]]
    taken = {v["layer"] for v in out}
    for f, v in new.items():
        nm = name_of(v["companies"], f)
        v["layer"] = nm if nm not in taken else f"{nm}, by revenue model"
        taken.add(v["layer"])
    rest_at = next((i for i, v in enumerate(out) if v.get("official")), len(out))
    out[rest_at:rest_at] = list(new.values())
    out = [v for v in out if v["companies"] or not v.get("official") or v.get("basis") != "rest"]

    # 2. size: no catch-all above SPLIT_SHARE of the placed companies when a split is possible
    total = sum(len(v["companies"]) for v in out)
    split_out: set = set()          # R41: companies placed after the map that this split by model moved out of the layer they were placed in
    for _ in range(4):
        # a half of an earlier split isn't halved again (R26: a catch-all of mostly unknown models became "… (smaller) (smaller)")
        big = next((v for v in out if not v.get("official") and not v.get("scale") and len(v["companies"]) >= SPLIT_MIN
                    and len(v["companies"]) > SPLIT_SHARE * total and not MIXED_SCALE.search(v.get("layer") or "")), None)
        if big is None:
            break
        at = out.index(big)
        cos = big["companies"]
        fines = Counter(models[c["ticker"]] for c in cos if c.get("ticker") in models)
        parts = [m_ for m_, n in fines.most_common() if n >= SPLIT_PART]
        if len(parts) >= 2:
            add = []
            for m_ in parts[1:]:
                mine = [c for c in cos if models.get(c.get("ticker")) == m_]
                split_out |= {c.get("ticker") for c in mine if c.get("placed")}
                cos = [c for c in cos if models.get(c.get("ticker")) != m_]
                same = next((v for v in out if v is not big and v["layer"] == MODELS[m_][1]), None)
                if same is not None:
                    same["companies"] += mine
                else:
                    add.append(_model_layer(MODELS[m_][1], mine))
            big["companies"] = cos
            out[at + 1:at + 1] = add
            continue
        ranked = sorted(cos, key=lambda c: (-(c.get("cap") or 0), c.get("ticker") or ""))
        half = len(ranked) // 2
        if half < SPLIT_PART:
            break
        name = big["layer"]
        small = _model_layer(f"{name} (smaller)", ranked[half:], scale="smaller", sibling=f"{name} (larger)")
        out[at] = {**big, "layer": f"{name} (larger)", "companies": ranked[:half], "scale": "larger", "sibling": small["layer"]}
        out.insert(at + 1, small)

    out = scale_bands(out)
    # 3. no layer of one company made by the split (R27: the live R26 IT deck had a visa and e-governance firm alone, a full page, as
    # "Hotels, travel and consumer services")
    out = _no_single_layers(out, before, main, fam, theme, fits)
    # c1 (R44): the companies left in "Other" placed where their own words or official industry name a layer's business (from_other)
    out = from_other(out, models, conf, every, fam, main, ev, theme_words, outside)

    # 3b. R31: no two layers of one primary model (the live R30 Semiconductors deck had "Fabless chip design" beside "Product designers that
    # outsource making"): a layer the split made joins the map's own layer of its primary model, family and sub-basis
    def primary(cos):
        f = main(cos)
        known = [c for c in cos if fam(c) == f] if f else []
        if not known or len(known) * 2 < len(cos):
            return None
        fines = {models[c["ticker"]] for c in known}
        return (next(iter(fines)) if len(fines) == 1 else f, f, sub_basis(f, [ev(c) for c in known]))
    keys = {id(v): primary(v["companies"]) for v in out if not v.get("official") and v["companies"]}
    model_names = {x[1] for x in MODELS.values()} | {x[0] for x in FAMILIES.values()}
    by_how = lambda x: x.get("by_model") or x["layer"] in model_names or x["layer"].removesuffix(", by revenue model") in model_names     # noqa: E731
    groups: dict = {}
    for v in out:          # a half of a split by size stays
        k = keys.get(id(v))
        if k and k[2] != "mixed" and not v.get("official") and not v.get("scale"):
            groups.setdefault(k, []).append(v)
    gone, lone = set(), []
    for grp in groups.values():
        named = [x for x in grp if by_how(x)]
        if len(grp) < 2 or not named:
            continue
        plain = [x for x in grp if not by_how(x)]
        # R36 (live R32 Semiconductors: Qorvo, IPG Photonics, a chip materials supplier and six more makers shown under "Semiconductor
        # equipment", the larger of the map's two layers of makers): when the map itself keeps two layers that earn this way apart by what
        # they make, how a company earns doesn't say which of them it belongs to, so the model-named layers become one and stay beside them
        target = max(plain if len(plain) == 1 else named, key=lambda x: len(x["companies"]))
        for v in named:
            if v is not target:
                # R39 (lane s1-fit; the live R37 Semiconductors deck: Micron, Intel, SK Hynix, lasers and LED makers, 13 companies of a split
                # layer, joined "Semiconductor equipment" because both make their own products): a layer the split made joins the map's own
                # layer only with the companies whose own words share what that layer's name or description says is made or done; the others
                # keep their layer, and one left alone goes to the theme's "Other" group (no layer of one company: R27)
                # R41 (lane s2-exact, the live Release 38.1 Semiconductors deck: Qorvo, placed by the answer with the chip designers, split
                # out with the makers by how it earns, joined "Semiconductor equipment" as if the map had placed it with them): a company placed
                # after the map that the split by model moved out of its layer joins only when it fits, like one moved by how it earns (the
                # companies the map itself named keep joining as before: R31's managed-service firms)
                ok = lambda c: by_how(target) or not (c.get("moved") or c.get("ticker") in split_out) or fits(c, target)      # noqa: E731
                fit = [c for c in v["companies"] if ok(c)]
                left = [c for c in v["companies"] if not ok(c)]
                target["companies"] += [{**c, "moved": True} for c in fit]
                if len(left) == 1:
                    lone.append({**left[0], "moved": True, "single": True, "fit": True})
                    left = []
                v["companies"] = left
                if not left:
                    gone.add(id(v))
    out = [v for v in out if (v["companies"] or not v.get("by_model")) and id(v) not in gone]
    if lone:
        other = next((x for x in out if x.get("official") and x.get("basis") == "rest"), None)
        if other is None:
            other = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
            out.append(other)
        other["companies"] += lone
    out = sold_what(out, placed_in, by_how, main, fam, ev, theme_words, theme, previous, lambda c: models.get(c.get("ticker")), moved_before,
                    published)

    # ex49 (R48, the outside review of the live Release 48 decks: "distinguish a real difference in revenue model from insufficient evidence or
    # partial comparability; never use them interchangeably"): why a company listed in a layer is left out of its figures, precisely:
    # "off_industry" (its own words describe another business than its official industry files it under), "model" (its way of earning, read
    # from the answer or its own words, is another than the layer's), "weak" (its way of earning is read only with low confidence), "no_words"
    # (no description of its own is stored), "no_model" (its own words don't state how it earns)
    unfit_all: set = set()
    word_other: dict = {}          # x57: no model read, its principal words state another way of earning than its layer's: {symbol: model}

    def out_why(c) -> str:
        s_ = c.get("ticker")
        if s_ in unfit_all:
            return "unfit"
        if s_ in another:
            return "off_industry"
        if fam(c) or s_ in outside or s_ in word_other:
            return "model"
        # gl52 (R52, the rotating review of Release 51: Trade-Wings and Yaan "read only weakly", though no word of theirs was ever read): a
        # company with no words of its own has no description to read, whatever an answer on its name gave
        if not own_text(ev(c)).strip():
            return "no_words"
        if conf.get(s_) == "low" and every.get(s_):
            return "weak"
        return "no_model"

    # x57 (second wave, the release gate's "model contradicted"): a read of low or medium confidence that the company's own words contradict
    # (they state another way of earning in so many words, of another family, and show nothing of the read: theme_check.contradicted_read)
    # gives way to the way its words state, at "medium", for what is printed and for its layer's figures; set after every move, so it moves
    # no company to another layer
    from .theme_check import contradicted_read

    def whole_ev(c) -> str:
        # its whole stored description (`about_of`), never only the first characters the model evidence keeps, its industry line first
        try:
            whole = str(about_of(c.get("ticker")) or "") if about_of is not None else ""
        except Exception:
            whole = ""
        return f"Industry: {c.get('industry')}. {whole}" if whole and c.get("industry") else (whole or ev(c))
    for v in out:
        for c in v["companies"]:
            s_ = c.get("ticker")
            if s_ in every and s_ not in another:
                st_ = contradicted_read(every[s_], whole_ev(c), conf.get(s_, ""))
                if st_:
                    every[s_], conf[s_], models[s_] = st_, "medium", st_
                    outside.discard(s_)

    # 4. what each layer's companies have in common, and who is left out of its figures
    # gl52 (R52, the integrator, on the Capital goods replay: 128 "Industrial Products" companies with no words of their own counted on their
    # industry in "Engines and industrial machinery makers", though that industry is spread over several layers): where the theme's companies
    # of an industry that were read (words of their own) or placed by the AI (its answer or the map's own pick) sit, by layer (a layer's two
    # halves by market value are one layer); a company with no words counts on its industry only in a layer that holds most of them
    # (industry_points_here)
    base_of = lambda w: _HALF_RX.sub("", w.get("layer") or "")      # noqa: E731
    read_where: dict = {}
    for w in out:
        if w.get("official"):
            continue
        for x in w["companies"]:
            if x.get("industry") and (own_text(ev(x)).strip() or x.get("placed") != "words"):
                read_where.setdefault(key(x["industry"]), Counter())[base_of(w)] += 1

    def industry_points_here(c, v) -> bool:
        where_ = read_where.get(key(c.get("industry"))) or Counter()
        here_ = where_[base_of(v)]
        return here_ >= ON_INDUSTRY_MIN and here_ >= ON_INDUSTRY_SHARE * sum(where_.values())
    # r572: the theme's TOP_MEMBERS largest companies by market value (by_model `map_`)
    caps_ = {c.get("ticker"): c.get("cap") or 0 for w in out for c in w["companies"] if c.get("ticker")}
    top_members = {t_ for t_, cap in sorted(caps_.items(), key=lambda kv: (-kv[1], kv[0]))[:min(TOP_MEMBERS, len(caps_) // TOP_SHARE)] if cap}
    for v in out:
        v["companies"] = [{**c, "model": every.get(c.get("ticker"), ""), "model_tags": list(tags.get(c.get("ticker")) or []),
                           "model_confidence": conf.get(c.get("ticker"), "") if c.get("ticker") in every else ""} for c in v["companies"]]
        if v.get("official"):
            continue
        cos = v["companies"]
        # gl52 (R52): an AI placement or map pick whose own words and official industry both contradict what this layer is (definition_fit
        # "unfit") is listed here but left out of its figures, as another business than the layer's
        uf = {c.get("ticker") for c in cos if isinstance(c.get("unfit"), dict)
              and c["unfit"].get("layer") in (_HALF_RX.sub("", v.get("layer") or ""), v.get("was"))}
        for s_ in uf:
            models.pop(s_, None)
            outside.add(s_)
        unfit_all.update(uf)
        f = main(cos)
        known = [c for c in cos if fam(c) == f] if f else []
        if not known:
            if cos:          # R26: said plainly, never left blank beside layers that have a line
                line = (f"None of these {len(cos)} companies' descriptions shows how it earns, so no common way of earning is given for this group."
                        if len(cos) > 1 else "Its description doesn't show how it earns.")
                if v.get("scale"):
                    line += f" The {v['scale']} half of one group by market value; the other half is “{v['sibling']}”."
                v["model"] = {"id": "", "family": "", "line": line, "known": 0, "of": len(cos), "sparse": True}
            continue
        fines = {models[c["ticker"]] for c in known}
        mid = next(iter(fines)) if len(fines) == 1 else f
        what = MODELS[mid][2] if mid in MODELS else FAMILIES.get(f, ("", MODELS[sorted(fines)[0]][2]))[1]
        # R40 (the owner's review of the live Release 39 Automotive deck: Bosch and Asahi India Glass, in "Component and systems suppliers",
        # left out of its figures as another business because they were read as makers of their own products): in a layer whose companies
        # are all of one official industry, a company of it whose model is of the layer's kin (making: its own products or parts and
        # components) is in the layer's figures; never one of another business than its industry files it under (off_industry)
        inds_ = {key(c.get("industry")) for c in cos}
        kin = {c.get("ticker") for c in cos if fam(c) != f and c.get("ticker") not in another and len(inds_) == 1 and "" not in inds_
               and any({f, model_family(read.get(c.get("ticker")))} <= k_ for k_ in KIN_FAMILIES)}
        # d1 (the outside review of the live Release 41 decks: a company left out of its layer's figures for want of a stored description):
        # one with no description of its own, of the layer's way of earning or of none shown, whose official industry is that of most of the
        # layer's companies and of no other layer of the map (an unambiguous fit), is in the layer's figures on its industry, and says so
        # ("on_industry"); one whose own words show how it earns only weakly stays out (R27)
        top_ind = Counter(key(c.get("industry")) for c in known if c.get("industry")).most_common(1)
        # gl50 (R50, the rotating review: Nestle India, Mahindra & Mahindra, Zydus Lifesciences left out for want of a stored description): the
        # industry is unambiguous when it is the majority of no other layer of the map (it was: held by no other company of any other layer, so
        # one stray company elsewhere kept every company of a large industry with no description out of its layer's figures)
        elsewhere = {t[0][0] for w in out if w is not v and not w.get("official") and w["companies"]
                     for t in [Counter(key(x.get("industry")) for x in w["companies"] if x.get("industry")).most_common(1)]
                     if t and t[0][1] * 2 > len(w["companies"])}
        # gl52 (R52, the rotating review of Release 51: Nestle India out of "Branded packaged foods manufacturing (larger)", its words "operates
        # in the Food segment" stating no way of earning, and its industry held to be ambiguous because the layer's own other half has it too;
        # Global Payments, Block and TBO Tek out of their layers the same way): per company, its industry decides when it is the one most of
        # the layer's companies share (the layer's other half by market value is the same layer, never "elsewhere"), or the layer's own name or
        # description names it, whatever other layers hold; and a company whose words exist but state no way of earning other than the layer's
        # is judged the same as one with none. One whose words state another way of earning, or read only weakly, stays out (R27)
        half_of = lambda w: bool(v.get("scale")) and _HALF_RX.sub("", w.get("layer") or "") == _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
        elsewhere_ = {t[0][0] for w in out if w is not v and not w.get("official") and w["companies"] and not half_of(w)
                      for t in [Counter(key(x.get("industry")) for x in w["companies"] if x.get("industry")).most_common(1)]
                      if t and t[0][1] * 2 > len(w["companies"])}
        def ind_decides(c) -> bool:
            k_ = key(c.get("industry"))         # most of the companies shown to earn the layer's way are of its industry
            if top_ind and k_ == top_ind[0][0] and top_ind[0][1] * 2 > len(known) and k_ not in elsewhere_:
                return True
            # the layer's own name (shown or the map's) names it; never its description alone ("product design, embedded software" names
            # no "Software Products" layer)
            return industry_named_by({"layer": v.get("layer"), "was": v.get("was")}, c.get("industry"), theme_words)

        def no_way_said(c) -> bool:
            if not own_text(ev(c)).strip():
                return True
            return not (every.get(c.get("ticker")) and conf.get(c.get("ticker")) == "low") and said_(c) <= {f}
        said_ = lambda c: {model_family(x) for x in words_models(ev(c))} - {""}      # noqa: E731
        # a company with no words: the gl50 rule as it was (its industry the majority of the layer's companies shown to earn its way and of
        # no other layer, the layer's own other half counted), else only where that industry points mostly to this layer (industry_points_here)
        r50_ind = lambda c: bool(top_ind) and key(c.get("industry")) == top_ind[0][0] and top_ind[0][1] * 2 > len(known) \
            and top_ind[0][0] not in elsewhere      # noqa: E731
        on_ind = {c.get("ticker") for c in cos if fam(c) == "" and c.get("ticker") not in another and c.get("ticker") not in outside
                  and c.get("industry") and ind_decides(c) and no_way_said(c)
                  and (own_text(ev(c)).strip() or r50_ind(c) or industry_points_here(c, v))
                  and model_family(every.get(c.get("ticker")) or "") in ("", f)}
        kin |= on_ind
        # ex49 (R48, the outside review of the live Release 48 Consumer retail deck: lululemon, in "Apparel and consumer brand owners" by
        # its own words, left out of that layer's figures as "another business"): a company read as a retailer, whose own words say it
        # designs the goods it sells, or makes them under its own brand (theme_check.own_goods), that the answer also read as a maker, and whose
        # words say this layer's name, sells products of its own: in a layer of makers it is in the figures, and says why ("own_goods").
        # Never one of another business than its industry files it under (off_industry)
        brand = {c.get("ticker") for c in cos if f == "making" and every.get(c.get("ticker")) == "retail" and c.get("ticker") not in another
                 and conf.get(c.get("ticker")) != "low" and any(model_family(t) == "making" for t in tags.get(c.get("ticker")) or [])
                 and own_goods(ev(c)) and layer_says(v, own_text(ev(c)), theme_words)[1]}
        kin |= brand
        # ex49 (R48, the rotating review of the live Release 48 decks, G3: Fortinet in "Network security appliances and subscriptions", Akamai
        # in "Cloud-delivered security and edge networks", Route Mobile in "Enterprise connectivity and messaging", each the map's own pick and
        # each left out as "other business"): a company of another way of earning that the map itself put in this layer (never one the split
        # moved there), whose own words say the layer's name and name no way of earning but the layer's, and whose model rests on no words of
        # its own ("high" confidence is words of its kind), differs from the layer only by the answer's read: it is in the figures, and says
        # so ("by_words"). So is one placed there after the map whose own words state the layer's way of earning in so many words (an
        # assembly and test services firm in "Outsourced packaging and test" read as a parts maker). One whose own words name another way
        # of earning (a design services firm in a software layer) stays out, as does one placed after the map whose words state none.
        said_ = lambda c: {model_family(x) for x in words_models(ev(c))} - {""}      # noqa: E731
        words_ = {c.get("ticker") for c in cos if fam(c) != f and c.get("ticker") not in kin and c.get("ticker") not in another
                  and every.get(c.get("ticker")) and model_family(every.get(c.get("ticker"))) != f and not c.get("moved")
                  and conf.get(c.get("ticker")) in ("medium",) and said_(c) <= {f} and (not c.get("placed") or said_(c) == {f})
                  and layer_says(v, own_text(ev(c)), theme_words)[1]}
        kin |= words_
        # gl52 (R52, the rotating review of Release 51: Syngene, "India's first Contract Research Organization", out of "Contract research and
        # life-science services" as read only weakly, though the answer's read was the layer's own way of earning; Fiserv, "processes debit
        # and credit card transactions", out of "Merchant acquiring and processing", read as managed IT services at low confidence): a company
        # read only at low confidence whose own words say the layer's name, and whose read or own words are of the layer's way of earning and
        # name no other, is in the figures on its words ("by_words"); one whose words name another way of earning stays out
        # x57 (R57, the audit of the 24 live R56 decks, RC4: Syngene, "India's first Contract Research Organization (CRO) ... (CRAMS)", in
        # its layer's figures in the Pharma deck and "insufficient evidence" in the Hospitals deck's "Contract research and life-science
        # services", the same stored words): a company read at low confidence as the layer's way of earning whose own words say the layer's
        # name has two signs of the layer's way; another way its words also name is what it also earns from (said on its row), never a
        # reason to call its evidence insufficient
        main_said = lambda c: {model_family(x) for x in words_models(principal_words(ev(c)))} - {""}      # noqa: E731

        def same_kin(fam_: str) -> bool:
            # r571x: the layer's own family, or one of its kin of making (a maker of its own products beside a parts maker)
            return bool(fam_) and (fam_ == f or any({f, fam_} <= k_ for k_ in KIN_FAMILIES))

        def of_layer(c) -> bool:
            # x57: a sign the company is of what the layer is, beside the read: its own words say the layer's name or share a word of its kind
            # with the layer's description, or its official industry is the layer's (never the read of how it earns alone)
            # (its industry counts only beside words that name what it makes or does, OF_LAYER_WORDS of them: "a financial group" names none)
            t_ = own_text(ev(c))
            return bool(layer_says(v, t_, theme_words)[1] or says_of_layer(v, t_, theme_words)
                        or (industry_fits(v, c.get("industry"), theme_words) and len(kind_stems(t_) - theme_words) >= OF_LAYER_WORDS))

        def way_named(fam_: str) -> bool:
            # x57: the layer's own name or description says the way of earning of its companies (a word of that way's name or of what it
            # earns from, MODELS), so saying the layer's name says how it earns
            lay_ = whole_stems(" ".join(str(x) for x in (_HALF_RX.sub("", v.get("layer") or ""), v.get("was"), v.get("description")) if x))
            way_ = set().union(*[whole_stems(f"{MODELS[m_][1]} {MODELS[m_][2]}") for m_ in MODELS if model_family(m_) == fam_] or [set()]) - _FIT_STOP
            return bool(lay_ & way_)
        weak_ = {c.get("ticker") for c in cos if fam(c) == "" and c.get("ticker") not in kin and c.get("ticker") not in another
                 and c.get("ticker") not in outside and conf.get(c.get("ticker")) == "low"
                 and (f in said_(c) or (model_family(every.get(c.get("ticker")) or "") == f and not said_(c)))
                 and layer_says(v, own_text(ev(c)), theme_words)[1]}
        kin |= weak_
        words_ |= weak_
        # x57 (RC4: Mahindra & Mahindra, PI Industries, BASF India, Zoom, AtriCure and Inspire, each read at low confidence as its layer's way
        # of earning, each with a description that names its products and no other way of earning in the sentences that say its principal
        # business, left out as "insufficient evidence"): the layer it was placed in and the read of how it earns agree, and its own words
        # don't contradict them (the sentences on its subsidiaries' or other businesses are what it also earns from: principal_words): it is in
        # the layer's figures, marked as read at low confidence ("read_low"), never as shown in its own words
        low_ = {c.get("ticker") for c in cos if fam(c) == "" and c.get("ticker") not in kin and c.get("ticker") not in another
                and c.get("ticker") not in outside and c.get("ticker") not in uf and conf.get(c.get("ticker")) == "low"
                and own_text(ev(c)).strip() and ((same_kin(model_family(every.get(c.get("ticker")) or "")) and all(same_kin(x) for x in main_said(c))) or f in main_said(c))
                and of_layer(c)}
        kin |= low_
        # r571x (R57.1, the new live Aerospace and defense deck: GE Aerospace and RTX, read at low confidence as makers of their own products,
        # and Honeywell Aerospace, read as one at medium, left out of "Engines and propulsion", a layer read as parts makers): a maker of its own
        # products and a parts maker are one kin of making (KIN_FAMILIES); a company of the layer's kin whose own words or industry are of what
        # the layer is (of_layer) is in its figures, whatever the layer's industries (R40 asked one industry)
        # (a company the split held in this layer as another way of earning, its read set aside, counts by that read: `read`)
        kin_any = {c.get("ticker") for c in cos if c.get("ticker") not in kin and c.get("ticker") not in another and c.get("ticker") not in uf
                   and (fam(c) or c.get("ticker") in outside) and model_family(models.get(c.get("ticker")) or read.get(c.get("ticker")) or "") != f
                   and same_kin(model_family(models.get(c.get("ticker")) or read.get(c.get("ticker")) or "")) and of_layer(c)}
        for s_ in kin_any:
            outside.discard(s_)
            models.setdefault(s_, read.get(s_) or every.get(s_) or "")
        kin |= kin_any
        # x57 (RC4: Payoneer, "remove the complexity and barriers of doing business across borders", in "Cross-border and B2B payments" with no
        # way of earning read): a company no answer gave a model, placed in the layer by the map or the AI's placement (never by its words
        # alone), whose own words say the layer's name and name no way of earning, in a layer whose own name and description state no way of
        # earning but its companies' own, is in its figures on its words ("by_words", the layer's way at low confidence); one whose principal
        # words state another way of earning is left out as that different way (word_other), never as insufficient evidence
        nm_kinds = {model_family(x) for x in name_models(_HALF_RX.sub("", v.get("layer") or "")) | name_models(v.get("was") or "")
                    | words_models(v.get("description") or "")} - {""}
        bare_ = {c.get("ticker") for c in cos if fam(c) == "" and c.get("ticker") not in kin and c.get("ticker") not in another
                 and c.get("ticker") not in outside and c.get("ticker") not in uf and not every.get(c.get("ticker"))
                 and c.get("placed") != "words" and not c.get("moved") and own_text(ev(c)).strip() and not said_(c)
                 and nm_kinds <= {f} and way_named(f) and len(known) * 2 >= len(cos) and layer_says(v, own_text(ev(c)), theme_words)[1]}
        kin |= bare_
        words_ |= bare_
        # r62 (the live R60 Electric utilities deck: Southern, the theme's largest company, "the traditional electric operating companies ...
        # are each vertically integrated utilities", NiSource, "fully regulated natural gas and electric utility companies", and 13 more left
        # out of "Regulated vertically integrated utilities" as insufficient evidence): a company no answer read, of the industry most of the layer's companies shown to
        # earn its way share (ind_decides), whose own words state the layer's way of earning, among others, and say a word of the layer's own
        # name, is in its figures on its words ("by_words"); the other ways its words name are what it also earns from, said on its row
        ind_words_ = {c.get("ticker") for c in cos if fam(c) == "" and c.get("ticker") not in kin and c.get("ticker") not in another
                      and c.get("ticker") not in outside and c.get("ticker") not in uf and c.get("industry")
                      and model_family(every.get(c.get("ticker")) or "") in ("", f)
                      and bool(top_ind) and key(c.get("industry")) == top_ind[0][0] and top_ind[0][1] * 2 > len(known)
                      # (an industry "most" of the read companies share is two or more of them: one read company of four is no majority
                      # the others' industry can rest on, and the layer says it rests on under half its companies, Release 63 CI)
                      and top_ind[0][1] >= 2
                      # (its words say the layer's own name, naming no way of earning or the layer's among others; or they state the
                      # layer's way of earning and no other: "fully regulated natural gas and electric utility companies")
                      and ((layer_says(v, own_text(ev(c)), theme_words)[1] and (not said_(c) or f in said_(c))) or said_(c) == {f})}
        kin |= ind_words_
        words_ |= ind_words_
        bare_ |= ind_words_
        # r572 (R57.2, the live R57.1 decks: McDonald's, the Restaurants theme's largest company, and Yum left out as "insufficient
        # evidence"; SLB, Baker Hughes, Halliburton and 13 more of 18 in "Oilfield services and equipment"; Disney in "Broadcast, cable networks
        # and studios"; TVS Supply Chain in "Contract logistics and supply chain managers"): a company the map or the AI's placement put in this
        # layer (never one the split moved here by a read of how it earns), not read at medium or high confidence as another way, whose own
        # principal words name no other way of earning, and that is one of the theme's TOP_MEMBERS largest companies or larger than every
        # company in the layer's figures, is in the layer's figures: nothing it says contradicts the layer ("by_map"), and insufficient
        # evidence alone never leaves the largest out. One whose words state another way stays out, as that way
        cap_ = lambda c: c.get("cap") or 0      # noqa: E731
        in_ = {x.get("ticker") for x in known} | kin
        top_in = max((cap_(c) for c in cos if c.get("ticker") in in_), default=0)
        # (an AI placement or map pick held "unfit" only for want of words that fit the layer is no contradiction: definition_fit)
        map_ = {c.get("ticker") for c in cos if (fam(c) == "" or c.get("ticker") in uf) and c.get("ticker") not in kin
                and c.get("ticker") not in another and (c.get("ticker") not in outside or c.get("ticker") in uf) and not c.get("moved")
                and (conf.get(c.get("ticker")) == "low" or model_family(every.get(c.get("ticker")) or "") in ("", f))
                and all(same_kin(x) or x == "holding" for x in main_said(c))
                and model_family(stated_model(principal_words(ev(c)))) in ("", f, "holding")
                and (c.get("ticker") in top_members or (cap_(c) > top_in > 0))}
        kin |= map_
        for c in cos:
            s_ = c.get("ticker")
            if fam(c) == "" and s_ not in kin and s_ not in another and s_ not in outside and s_ not in uf \
                    and (not every.get(s_) or (conf.get(s_) == "low" and model_family(every[s_]) != f)) and own_text(ev(c)).strip() \
                    and main_said(c) - {f} and f not in said_(c) and model_family(stated_model(principal_words(ev(c)))) not in ("", f):
                word_other[s_] = stated_model(principal_words(ev(c)))          # one way stated in so many words, never a guess
        # its model is the one its own words state (never the low read of another family: Fiserv is no managed IT services firm)
        word_model = {c.get("ticker"): next(iter(sorted(m_ for m_ in words_models(ev(c)) if model_family(m_) == f)), "")
                      for c in cos if c.get("ticker") in weak_ and model_family(every.get(c.get("ticker")) or "") != f}
        # gl52 (R52, the rotating review of Release 51: L&T and KEC, "engineering, procurement and construction (EPC)", left out of "Power
        # equipment makers and EPC contractors" as "a different revenue model", the layer's figures being its makers'): a layer whose own name
        # states a second way of earning (NAME_PART_MODEL) takes in its figures a company of that way whose own words say the same name part,
        # and its line says so; never one of another business than its industry files it under
        nm_ = " ".join(x for x in (_HALF_RX.sub("", v.get("layer") or ""), v.get("was") or "") if x)
        part_ = {c.get("ticker") for c in cos if c.get("ticker") not in kin and c.get("ticker") not in another and c.get("ticker") not in uf
                 and every.get(c.get("ticker")) in NAME_PART_MODEL and model_family(every[c.get("ticker")]) != f
                 and re.search(NAME_PART_MODEL[every[c.get("ticker")]], nm_, re.I)
                 and (re.search(NAME_PART_MODEL[every[c.get("ticker")]], own_text(ev(c)), re.I) or of_layer(c))}
        kin |= part_
        words_ |= part_
        rest = [c for c in cos if fam(c) != f and c.get("ticker") not in kin]
        known_ids = {c.get("ticker") for c in known} | kin
        top_model = Counter(models[x["ticker"]] for x in known).most_common(1)[0][0]

        def read_of(c) -> dict:
            # x57: whether an answer read it as another way than the layer's (said: "only the AI's read gave it another"), or gave it none
            md_ = every.get(c.get("ticker"))
            return {} if md_ and model_family(md_) != f else {"read_agrees": True} if md_ else {"no_read": True}

        def also_of(c) -> dict:
            # x57 (RC4 c): the other ways of earning its own words name (its subsidiaries' and other businesses' among them), said on its row
            got = sorted({m_ for m_ in words_models(ev(c)) | secondary_models(ev(c)) if model_family(m_) and model_family(m_) != f})
            return {"also_earns": got} if got else {}
        v["companies"] = [({**c, "on_industry": True, "model": c.get("model") or top_model,
                            "model_confidence": c.get("model_confidence") or "low"} if c.get("ticker") in on_ind else
                           {**c, "own_goods": True} if c.get("ticker") in brand else
                           {**c, "by_words": True, **also_of(c), **read_of(c),
                            **({"model": word_model[c["ticker"]], "model_confidence": "medium"} if word_model.get(c.get("ticker")) else
                                                                    {"model": top_model, "model_confidence": "low"} if c.get("ticker") in bare_ else {})}
                           if c.get("ticker") in words_ else
                           {**c, "read_low": True, **also_of(c)} if c.get("ticker") in low_ or (c.get("ticker") in named_low and own_text(ev(c)).strip()) else
                           {**c, "by_map": True, "no_words": True} if c.get("ticker") in named_low else
                           {**c, "by_map": True, **also_of(c), **read_of(c), **({} if own_text(ev(c)).strip() else {"no_words": True})}
                           if c.get("ticker") in map_ else c) if c.get("ticker") in known_ids else
                          {**c, "model_out": "other" if fam(c) or c.get("ticker") in outside or c.get("ticker") in word_other else "unknown",
                           **({"model": word_other[c["ticker"]], "model_confidence": "medium"} if word_other.get(c.get("ticker")) else {}),
                           "out_why": out_why(c)} for c in cos]      # R34: why, named; ex49: precisely (out_why)
        known = known + [c for c in cos if c.get("ticker") in kin]
        away_ = {c.get("ticker") for c in rest if fam(c) or c.get("ticker") in outside}      # cl48: listed as another way of earning
        sparse = len(known) * 2 < len(cos)
        if sparse:
            # R26: a line resting on a few of a layer's companies isn't what they have in common: said plainly instead (the live R25 IT services
            # deck, "8 of 50; the others' descriptions don't show how they earn"); R27: the others are left out of its figures
            # gl52 (R52, the rotating review of Release 51: "shown for only 2 of these 15 companies, mainly fees paid by consumers for stays,
            # trips, meals or courses" on a layer of diagnostics labs): a way of earning shown for fewer than MODEL_LINE_MIN companies is
            # not said to be what the layer's companies mainly earn by
            line = (f"How they earn is shown for only {len(known)} of these {len(cos)} companies, mainly {what}; " if len(known) >= MODEL_LINE_MIN else
                    f"How they earn is shown for only {len(known)} of these {len(cos)} companies; ") + out_line(rest, 'the other', away_)
        else:
            line = f"They earn mainly from {what}."
            if rest:
                line += " " + out_line(rest, f"of {len(cos)}", away_)
        also = also_earn(known, f)
        if also:
            n_, t_ = also
            line += f" {n_} of the {len(known)} also earn{'s' if n_ == 1 else ''} from {MODELS[t_][2]}."      # r69e: "1 of the 5 also earns"
        if part_:
            pm_ = every[sorted(part_)[0]]
            line += (f" {len(part_)} of them earn{'s' if len(part_) == 1 else ''} from {MODELS[pm_][2]}, a way of earning the layer's own name "
                     f"states too, and {'is' if len(part_) == 1 else 'are'} in its figures by {'its' if len(part_) == 1 else 'their'} own words.")
        if v.get("scale"):
            line += f" The {v['scale']} half of one group by market value; the other half is “{v['sibling']}”."
        sub = sub_basis(f, [ev(c) for c in known])
        # ex49 (R48, the outside review of the live Release 48 Chemicals deck: "Custom synthesis manufacturers" ranked against commodity
        # intermediates, both read as makers of their own products): the business model the map's own name for the layer states in so many
        # words (theme_check.stated_model: "custom synthesis", "contract manufacturing", "foundry"), when it is of another family than how its
        # companies are read to earn ("named"): such a layer is ranked only beside layers of that same business model (theme_data.one_business)
        named = next((x for x in (stated_model(v.get("was") or ""), stated_model(_HALF_RX.sub("", v.get("layer") or ""))) if x in MODELS), "")
        v["model"] = {"id": mid, "family": f, "line": line, "known": len(known), "of": len(cos), "out": len(rest),
                      "also": [{"id": also[1], "n": also[0]}] if also else [], **({"sparse": True} if sparse else {}), **({"sub": sub} if sub else {}),
                      **({"named": named} if named and model_family(named) != f else {})}
        # R40 (the owner's review of the live Release 39 Semiconductors deck: "Makers of their own products", memory, optical and analog chip
        # makers the split grouped by how they earn, ranked beside the map's layers): a layer the split made and named only by how its
        # companies earn is shown, never ranked (theme_data.headline_ok)
        if v.get("by_model") and not v.get("scale") and v["layer"].removesuffix(", by revenue model") in model_names:
            v["model"]["by_how"] = True
            # c1 (R44, the outside review of the live Release 43 Semiconductors deck: "Makers of their own products" mixes memory, processor,
            # laser and optics makers): the reason it is never ranked, on its own page (no group of it holds the 5 companies a ranking needs)
            if BY_HOW_SAID not in v["model"].get("line", ""):
                v["model"]["line"] = (v["model"].get("line") or "").rstrip() + " " + BY_HOW_SAID
    # R31: two of the map's own layers of one primary model, family and sub-basis both stay (the map groups them by what they make or serve);
    # each one's line says so, so no reader takes them for two ways of earning
    mine = [v for v in out if not v.get("official") and not v.get("scale") and (v.get("model") or {}).get("id") and not v["model"].get("sparse")
            and v["model"].get("sub") != "mixed"]
    for v in mine:
        same = [x["layer"] for x in mine if x is not v and all(x["model"].get(k) == v["model"].get(k) for k in ("id", "family", "sub"))]
        if same:
            v["model"]["same_as"] = same
            v["model"]["line"] += (" Its companies earn the same way as those of " + ", ".join(f"“{x}”" for x in same)
                                   + "; the map keeps them as separate layers.")
    return out


def unsplit_unshown(vc: list[dict], shown: set) -> list[dict]:
    """The layers with a split by market value undone where one of its halves has no company the deck shows (R32: the live R31 Real estate
    deck had "Residential developers (larger)" and "No listed company is shown for Residential developers (smaller)"): one layer of both
    halves' companies, the map's name, no "(larger)"/"(smaller)", its line counted again over them without the halves' words. `shown`: the
    symbols the deck shows (confirmed, with figures).
    R40 (the owner's review of the live Release 39 Automotive deck: "Component and systems suppliers (smaller)" showed ONE company of its 69,
    the others beyond the dive's figures, theme_base.FIGURES_MAX, the largest first): undone too where a half shows fewer than SPLIT_PART
    companies in its figures (shown, not left out by how it earns), the floor the split itself keeps for each part."""
    out = list(vc)
    for v in vc:
        if v.get("scale") != "larger":
            continue
        sib = next((x for x in out if x.get("scale") == "smaller" and x.get("layer") == v.get("sibling")), None)
        if sib is None or all(sum(1 for c in x.get("companies") or [] if c.get("ticker") in shown and not c.get("model_out")) >= SPLIT_PART
                              for x in (v, sib)):
            continue
        cos = list(v.get("companies") or []) + list(sib.get("companies") or [])
        merged = {k: x for k, x in v.items() if k not in ("scale", "sibling")}
        merged.update(layer=re.sub(r" \(larger\)$", "", v["layer"]), companies=cos)
        md = next((x["model"] for x in (v, sib) if (x.get("model") or {}).get("id")), None) or v.get("model")
        if md:
            line = re.sub(r" The (?:larger|smaller) half of one group by market value; .*$", "", str(md.get("line") or ""))
            md = {**md, "line": line, "of": None}
            md = shown_model(md, [{**c, "model": c.get("model", "")} for c in cos])
            if md.get("of") is None:
                md["of"] = len(cos)
            merged["model"] = md
        out[out.index(v)] = merged
        out.remove(sib)
    return out


def out_line(rest: list[dict], of: str, other=frozenset()) -> str:
    """How many of a layer's companies are left out of its figures and rankings, and why (R27): their model unknown, or of low confidence.
    cl48 (R47): one listed there as another way of earning or another business (model_out "other", or in `other`) is said to earn
    another way, never to have evidence that doesn't show how it earns."""
    n = len(rest)
    away = [c for c in rest if c.get("model_out") == "other" or c.get("ticker") in other]
    left = [c for c in rest if c not in away]
    k, u = len(away), len(left)
    low = sum(1 for c in left if c.get("model_confidence") == "low")
    why = ("doesn't show how it earns" if u == 1 else "doesn't show how they earn") if not low else \
          ("shows how it earns only weakly" if u == 1 else "shows how they earn only weakly") if low == u else \
          "doesn't show, or only weakly shows, how they earn"
    own_ = lambda m: 'its' if m == 1 else 'their'      # noqa: E731
    earns = f"{'it earns' if k == 1 else 'they earn'} another way than the layer's companies"
    reason = (f"as {own_(u)} evidence {why}" if not k else f"as {earns}" if not u
              else f"{k} as {earns}, {u} as {own_(u)} evidence {why}")
    if of.startswith("the other"):
        return f"the other {n} {'is' if n == 1 else 'are'} listed but left out of this layer's figures and rankings, {reason}."
    return f"{n} {of} {'is' if n == 1 else 'are'} listed but left out of this layer's figures and rankings, {reason}."


def also_earn(known: list[dict], family: str) -> tuple[int, str] | None:
    """(how many, model) the commonest secondary way of earning of a layer's companies outside the layer's own family (R27), or None."""
    from collections import Counter

    from .theme_check import model_family
    counts, first = Counter(), {}
    for i, c in enumerate(known):
        for t in c.get("model_tags") or []:
            if model_family(t) and model_family(t) != family:
                counts[t] += 1
                first.setdefault(t, i)
    if not counts:
        return None
    t = min(counts, key=lambda t: (-counts[t], first[t]))
    return counts[t], t


def shown_model(model: dict | None, rows: list[dict]) -> dict | None:
    """The layer's "how they earn" line counted over the companies its page shows (R28: the live R27 IT deck said "shown for only 6 of these
    46 companies" on a page of 6: the 46 were every company the map put in the layer, most with no figures worked out). `rows`: the layer's
    confirmed companies with figures, carrying model, model_tags, model_confidence and model_out (theme_data.model_fields). Unchanged when
    the counts already agree or the layer carries no model."""
    if not model or not rows or not any("model" in r for r in rows):
        return model
    from .theme_check import FAMILIES, MODELS
    if len(rows) == model.get("of"):
        return model
    f, mid = model.get("family") or "", model.get("id") or ""
    known = [r for r in rows if r.get("model") and not r.get("model_out")] if f else []
    rest = [r for r in rows if r not in known]
    n = len(rows)
    if not known:
        line = (f"None of these {n} companies' descriptions shows how it earns, so no common way of earning is given for this group."
                if n > 1 else "Its description doesn't show how it earns.")
        half = re.search(r" The (?:larger|smaller) half of one group by market value; .*$", str(model.get("line") or ""))
        return {**model, "line": line + (half.group(0) if half else ""), "known": 0, "of": n, "out": len(rest), "sparse": True, "also": []}
    what = MODELS[mid][2] if mid in MODELS else FAMILIES.get(f, ("", ""))[1]
    sparse = len(known) * 2 < n
    if sparse:
        line = f"How they earn is shown for only {len(known)} of these {n} companies, mainly {what}; {out_line(rest, 'the other')}"
    else:
        line = f"They earn mainly from {what}." + (" " + out_line(rest, f"of {n}") if rest else "")
    also = also_earn(known, f)
    if also:
        line += f" {also[0]} of the {len(known)} also earn{'s' if also[0] == 1 else ''} from {MODELS[also[1]][2]}."      # r69e
    # r64e (the US Steel and metals replay: "Metals distributors and mining developers" with Reliance and Ryerson in its figures by the way
    # of earning its name states, its page's line saying only the miners' way): the sentence on a way the layer's own name states (by_model,
    # NAME_PART_MODEL) stays, counted over the companies shown
    part = re.search(r" \d+ of them earns? from (.+?), a way of earning the layer's own name states too, and", str(model.get("line") or ""))
    if part:
        from .theme_check import model_family
        n_ = sum(1 for r in known if model_family(r.get("model") or "") not in ("", f))
        if n_:
            line += (f" {n_} of them earn{'s' if n_ == 1 else ''} from {part.group(1)}, a way of earning the layer's own name states too, and "
                     f"{'is' if n_ == 1 else 'are'} in its figures by {'its' if n_ == 1 else 'their'} own words.")
    half = re.search(r" The (?:larger|smaller) half of one group by market value; .*$", str(model.get("line") or ""))
    if half:                                   # the split's own words stay (by_model step 2)
        line += half.group(0)
    out = {**model, "line": line, "known": len(known), "of": n, "out": len(rest), "also": [{"id": also[1], "n": also[0]}] if also else []}
    out.pop("sparse", None)
    return {**out, "sparse": True} if sparse else out


# c1 (R44, the outside review of the live Release 43 Semiconductors deck: "Makers of their own products" mixes memory, processor, laser and
# optics makers): what a layer named only by how its companies earn says on its own page, in the words of the ranking's own reason
# (theme_data.RANK_WHY "how"); its companies stay together, as no group of them by what they make is confirmed by their words
BY_HOW_SAID = "Shown, never ranked: a group by how its companies earn, of different businesses."
# c1 (R44, the outside review of the live Release 43 decks: 29 of 90 Consumer retail companies and 32 of 65 Metals companies in "Other"):
# words that name one kind of goods ("apparel" says what "clothing" says), for a company's words read against a layer's name
SAME_KIND = ((r"\bapparel\b|\bgarments?\b", "clothing"),)
NO_ONE_BUSINESS = r"\b(?:misc\w*|other|others|diversified|nec|general)\b"      # an official industry naming no one kind of business


def _near(a: str, b: str) -> bool:
    """One stem says another: the same, or one of five letters or more starting the other (name_says)."""
    return a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))


def says_most_of(name: str, text: str, theme_words: set) -> bool:
    """Whether a company's words say two or more, and at least half, of the words of a layer's name beyond the theme's own (c1, R44: "a
    specialty clothing store" says two of "Family clothing stores"; "aluminium powder" says one of "Aluminium and copper smelting", "sells
    furniture online" one of "Online retailers" (R38: one shared word places nothing): neither is placed there by its words)."""
    rest = _stems(_short_joined(name)) - theme_words           # cl48 (R47): "off-price" one word, never said by "branched off"
    mine = _stems(_short_joined(text))
    said = sum(1 for b in rest if any(_near(a, b) for a in mine))
    return said >= 2 and 2 * said >= len(rest)


def industry_named(name: str, industry, theme_words: set) -> bool:
    """Whether a layer's name says all that an official industry's plain name says (c1, R44: "Zinc" in "Zinc, lead and silver mining and
    smelting", "Shipbuilding" in "Naval shipbuilding"; "Industrial minerals" is not all said by "Coal, iron ore and mineral mining")."""
    ind = kind_stems(plain_industry(industry)) - theme_words
    mine = kind_stems(str(name or "").lower().replace("-", " "))
    return bool(ind) and all(any(_near(a, b) for a in mine) for b in ind)


def no_words(evidence) -> bool:
    """Whether a company's evidence holds no words of its own about its work: none, or only the titles of its filings (theme_routes)."""
    return not own_text(evidence).strip()


def from_other(out: list[dict], models: dict, conf: dict, every: dict, fam, main, ev, theme_words: set, outside: set) -> list[dict]:
    """c1 (R44, the outside review of the live Release 43 decks: "improve coverage only with evidence; never force"): the companies left in
    the "Other" group after the split by how companies earn, placed where their own words or official industry name a business a layer
    covers, each marked with how ("by_industry" or "by_words"); every other one stays in "Other".
    1. One with no words of its own and no way of earning shown goes to the layer made of its official industry and named by it (by_model's
       industry group), else to the one layer whose name says all its official industry's name says (industry_named: "Coal" in "Mining of
       coal and iron ore") when that layer holds more than half of the theme's companies of that industry that have words of their own: an
       industry named by two layers ("Aluminium": a smelter's and a product maker's) or held mostly elsewhere places nothing.
    2. One whose way of earning is shown (not at "low") goes to the one layer of that way of earning whose name its own words say at least
       half of (says_most_of: "a specialty clothing store" says "Family clothing stores"; "apparel" says "clothing", SAME_KIND), and, in a
       family whose layers differ
       by a sub-basis (theme_check.SUB_BASIS: a metals company's commodity), only to a layer of its own (a ferro chrome maker never joins
       steelmaking by the word "steel").
    3. The companies of one official industry naming one kind of business (not "Miscellaneous", "Diversified"...) left in "Other" with no
       words or with words of one way of earning, with those of it the split moved from "Other" by that way of earning alone into a layer
       whose name their words don't say, make a layer of that industry when they are INDUSTRY_GROUP_MIN or more and SPLIT_PART or more of them
       have words of their own (never a layer of unread companies), and no company of that industry with words sits elsewhere (Metals: ten ferro
       alloy makers, five of them in "Mining of coal and iron ore" or "Other" by how they earn, five with no words, all "Ferro & Silica
       Manganese")."""
    from collections import Counter

    from .theme_check import SUB_BASIS, SUB_OF, off_industry, sub_basis
    rest_v = next((v for v in out if v.get("official") and v.get("basis") == "rest"), None)
    if rest_v is None or not rest_v["companies"]:
        return out
    layers = [v for v in out if not v.get("official") and v["companies"] and not v.get("scale")]      # never a half of a layer split by size
    name_of = lambda v: v.get("was") or v["layer"]          # noqa: E731
    group_ind = lambda v: key(v["companies"][0].get("industry")) if v.get("industry_group") else None      # noqa: E731
    worded: dict = {}
    for v in out:
        for c in v["companies"]:
            if c.get("industry") and not no_words(ev(c)):
                worded.setdefault(key(c["industry"]), Counter())[id(v)] += 1

    def kinded(text: str) -> str:
        for rx, to in SAME_KIND:
            text = re.sub(rx, to, text, flags=re.I)
        return text

    def sub_ok(c, v, f) -> bool:
        k_ = SUB_BASIS.get(f)
        if not k_:
            return True
        return SUB_OF[k_](ev(c)) == sub_basis(f, [ev(x) for x in v["companies"] if fam(x) == f])

    left = []
    for c in rest_v["companies"]:
        ind = key(c.get("industry")) if c.get("industry") else ""
        target, how = None, ""
        if c.get("ticker") in outside or off_industry(ev(c)):
            pass
        elif no_words(ev(c)) and not fam(c) and not every.get(c.get("ticker")) and ind:
            grp = [v for v in layers if group_ind(v) == ind]
            if grp:
                target, how = grp[0], "by_industry"
            elif not re.search(NO_ONE_BUSINESS, industry_label(c.get("industry")), re.I):
                said = [v for v in layers if industry_named(name_of(v), c.get("industry"), theme_words)]
                held = worded.get(ind) or Counter()
                if len(said) == 1 and held[id(said[0])] * 2 > sum(held.values()):
                    target, how = said[0], "by_industry"
        elif fam(c):
            f = fam(c)
            text = kinded(own_text(ev(c)))
            said = [v for v in layers if main(v["companies"]) == f and says_most_of(name_of(v), text, theme_words) and sub_ok(c, v, f)]
            if len(said) == 1:
                target, how = said[0], "by_words"
        if target is None:
            left.append(c)
        else:
            target["companies"].append({**c, "moved": True, "placed_by": how})
    rest_v["companies"] = left
    # 3. a layer of one official industry from "Other" and the companies the split moved by how they earn alone
    for ind in sorted({key(c.get("industry")) for c in left if c.get("industry")}):
        mine = [c for c in left if key(c.get("industry")) == ind]
        label = industry_label(mine[0].get("industry"))
        if re.search(NO_ONE_BUSINESS, label, re.I):
            continue
        fams = Counter(fam(c) for c in mine if fam(c))
        # moved by how it earns alone: the layer's name isn't said by its words, or its commodity isn't the layer's (SUB_BASIS)
        moved_in = [(v, c) for v in layers for c in v["companies"] if key(c.get("industry")) == ind and c.get("moved") and c.get("placed")
                    and fam(c) and not v.get("industry_group") and not v.get("scale")
                    and (not name_says(name_of(v), own_text(ev(c)), theme_words)[1] or not sub_ok(c, v, fam(c)))]
        fams.update(fam(c) for _, c in moved_in)
        if len(fams) != 1:
            continue
        f = next(iter(fams))
        grp = [c for c in mine if fam(c) == f or (no_words(ev(c)) and not every.get(c.get("ticker")))] + [c for _, c in moved_in]
        has_words = [c for c in grp if not no_words(ev(c))]
        ids = {id(c) for c in grp}
        elsewhere = sum(1 for v in out for c in v["companies"] if key(c.get("industry")) == ind and id(c) not in ids and not no_words(ev(c))
                        and fam(c) == f)
        if len(grp) < INDUSTRY_GROUP_MIN or len(has_words) < SPLIT_PART or elsewhere:
            continue
        for v, c in moved_in:
            v["companies"] = [x for x in v["companies"] if x is not c]
        rest_v["companies"] = [c for c in rest_v["companies"] if id(c) not in ids]
        out.insert(next((i for i, v in enumerate(out) if v.get("official")), len(out)),
                   {"layer": label, "description": "", "industry_group": True,
                    "companies": [{**c, "moved": True, "placed_by": "by_industry" if no_words(ev(c)) else "by_words"} for c in grp]})
    return out


def sold_what(out: list[dict], placed_in: dict, by_how, main, fam, ev, theme_words: set, theme: str, previous: dict | None = None,
              model_of=None, moved_before: dict | None = None, published: dict | None = None) -> list[dict]:
    """c54 (R53, the owner's review of the live R53 decks: Intel moved by how it earns from "Makers of their own products" into "Chip
    equipment and subsystem suppliers", Indo National into "Branded packaged foods manufacturing", UFP Technologies into "Surgical robotics
    systems"): each company new to a layer named by what it sells is checked against what that name defines (sells_layer: its own words of
    what it sells, or its official industry's name). New to a layer: its previous live layer (`previous`, the stored version before) is
    another, or the stored change log says a re-check moved it into this layer
    (`moved_before`: {symbol: [from, to]}, theme_changes.move_memory). One with no evidence of what the layer sells doesn't join it: it goes
    back to the layer it came from when that is a layer it is no misfit for, else to the layer named by its way of earning (where the
    companies of its way of earning that no layer's name defines are), else to the layer the map or the answer placed it in when it is no
    misfit there, else to "Other"; with the reason ("refit": the layer it would have joined, where it is, why). One the map or the answer
    itself placed there with nowhere to go back to stays, listed but left out of the layer's figures ("unfit").
    Not judged: a company that is where the stored version had it (a layer kept from one version to the next moves nobody), one with no words
    of its own (its industry decides, as before), one checked by its words or placed by them or its industry (from_other "placed_by",
    definition_fit "refit") or held to its previous layer, and a layer named by how its companies earn, made of one official industry, or
    whose name sells the theme's own product only qualified or names nothing (theme_product)."""
    named = [v for v in out if not v.get("official") and v.get("layer") and v["companies"]]
    names = lambda v: ({_HALF_RX.sub("", v.get("layer") or ""), v.get("was") or ""} | set(v.get("aka") or [])) - {""}      # noqa: E731
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    prev, before = previous or {}, moved_before or {}
    judged: dict = {}
    # r69e (LIVE13A-001 / LIVE13B-009, the live R67 Cement deck: Kanoria, "A.C. Pressure Pipes ... Asbestos Cement Products", and BigBloc,
    # "AAC Blocks", moved from "Other" into "Cement integrated producers (smaller)" by their official industry and way of earning, never
    # judged: a half of a layer split by market value is made by the split (by_model) and was skipped as a layer named by how it earns): a
    # half is judged as the layer it is a half of, by its name; and where that name is said by fewer than half of its companies' own words
    # (no test of what they sell), the theme's own product named as what the company makes now (says_theme_product, business_text) is
    def how_named(v):
        """Whether a layer is named by how its companies earn (by_how); a half by market value as the layer it is a half of."""
        if v.get("scale") in ("larger", "smaller"):
            big = next((w for w in out if w.get("scale") == "larger" and shown(w) == shown(v)), v)
            return bool(by_how({**big, "by_model": big.get("by_model") if big is not v or v.get("scale") == "larger" else False, "layer": shown(v)}))
        return bool(by_how(v))
    said_of: dict = {}

    def name_said(v) -> bool:
        if id(v) not in said_of:
            got = [sells_layer(v, named, sold_text(ev(x), x.get("name") or ""), None, theme_words) for x in v["companies"] if not no_words(ev(x))]
            said_of[id(v)] = bool(got) and sum(1 for g in got if g) * 2 >= len(got)
        return said_of[id(v)]

    def names_no_kind(v) -> bool:
        """Whether a layer's name says no kind of its own beyond the theme's product: only its scale, reach or structure ("Regional
        integrated producers", "Cement integrated producers"); "Branded packaged foods manufacturing" names foods."""
        words = [w for w in re.findall(r"[a-z]+", shown(v).lower()) if not (kind_stems(w) & theme_words)]
        return bool(words) and all(w in _STRUCTURE_WORDS for w in words)

    def went_out(c, v) -> bool:
        """The stored change log's last move took this company out of this layer (an earlier re-check's reason for moving it out)."""
        mb_ = before.get(c.get("ticker"))
        return isinstance(mb_, (list, tuple)) and len(mb_) == 2 and _HALF_RX.sub("", str(mb_[0] or "")) in names(v) \
            and _HALF_RX.sub("", str(mb_[1] or "")) not in names(v)

    def judge(c, v):
        k_ = (id(c), id(v))
        if k_ not in judged:
            judged[k_] = sells_layer(v, named, sold_text(ev(c), c.get("name") or ""), c.get("industry"), theme_words,
                                     (model_of(c) if model_of else c.get("model")) or "")
        return judged[k_]

    def came_from(c, v):
        """The layer a company is new to `v` from ("" for "Other" or not in the theme), or None when it is not new to `v`."""
        s_ = c.get("ticker")
        # r60 (the R60 replay of the live R59 IT services input: some twenty companies the R59 re-check moved into "Mid-tier digital
        # engineering and cloud services", published there, judged "new" again on the change log and sent to "Other": 80% -> 73% in
        # informative layers): a company the published version has in this layer is no newcomer to it; the placement contract keeps a
        # published member unless its own words contradict it
        mb_ = before.get(s_)
        from_none = isinstance(mb_, (list, tuple)) and len(mb_) == 2 and (not mb_[0] or str(mb_[0]).startswith("Other "))
        # e79 (LIVE15A-004, the live R77 Semiconductors re-check: OSI Systems, moved from "Other" into "Fabless chip design" on 18 Nov and
        # published there, kept by RULES 73 because its line "a vertically integrated designer and manufacturer of specialized electronic
        # systems" prints a word of the layer's name, "design", the act any trade does): one that came from "Other" stays as published only
        # where the layer's own test of what it sells (sells_layer, as now) doesn't say it sells something else; the rules of today judge a
        # carried move, never the line that printed it
        if _HALF_RX.sub("", str((published or {}).get(s_) or "")) in names(v) and not (prev.get(s_) and prev[s_] not in names(v)) \
                and (not from_none or (prints_layer(v, own_text(ev(c)), c.get("name") or "") and judge(c, v) is not False)) \
                and not any(w is not v and shown(w) != shown(v) and not by_how(w) and judge(c, w)
                            and prints_layer(w, own_text(ev(c)), c.get("name") or "") for w in named):
            # (one that joined from no layer on no line of its words, r59's JPMorgan, is still judged; so is one whose own words say what
            # another layer sells, in a line a deck prints: Gillette's "grooming and oral care" in packaged foods)
            return None
        if prev.get(s_) and prev[s_] not in names(v):
            return prev[s_]
        mb = before.get(s_)
        if isinstance(mb, (list, tuple)) and len(mb) == 2 and mb[1] in names(v) and mb[0] not in names(v):
            return mb[0] or ""
        # r581 (the R58 replay of Medical devices: American Shared Hospital Services, moved out of "Diagnostic and genetic testing labs" by
        # this rule on R58, put back by the split on the next check because the snapshot `previous` holds only the figures' companies):
        # one the last re-check moved out of this layer is new to it again, from where that re-check put it
        if isinstance(mb, (list, tuple)) and len(mb) == 2 and mb[0] in names(v) and mb[1] not in names(v) and not prev.get(s_):
            return mb[1] or ""
        return None

    def defined(v) -> str:
        """The words of a layer's name that define it, as the name says them ("“equipment” or “subsystem”")."""
        said = []
        for nm in dict.fromkeys(x for x in (shown(v), v.get("was")) if x):
            # each word as the name says it ("robotics", never the "robotic" it is read as)
            as_said = {(w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith("ss") else w): w
                       for w in re.findall(r"[a-z0-9]+", _short_joined(nm))}
            for p in _name_parts(nm):
                head, quals = p[-1], p[:-1]
                said.append("“" + " ".join(as_said.get(w, w) for w in (quals[-1:] + [head] if head in CATEGORY_WORDS | PART_WORDS and quals else [head]))
                            + "”")
        return " or ".join(dict.fromkeys(said))
    moves, unfit, sold = [], {}, {}
    for v in named:
        if v.get("industry_group") and not by_how(v):          # a layer of one official industry: in it by that industry, said so
            for c in v["companies"]:
                if came_from(c, v) is not None and not isinstance(c.get("refit"), dict):
                    sold[id(c)] = f"of its official industry, the one “{shown(v)}” is made of"
            continue
        if by_how(v) and how_named(v):
            continue
        newly = bool(by_how(v))          # r69e: a half by market value judged as the layer it is a half of (before: never judged)
        for c in v["companies"]:
            src = came_from(c, v)
            if src is None or isinstance(c.get("unfit"), dict) or isinstance(c.get("refit"), dict) or c.get("held"):
                continue
            mb_ = before.get(c.get("ticker")) if isinstance(before.get(c.get("ticker")), (list, tuple)) else None
            from_other = src == "" or str(src).startswith("Other ") or bool(
                mb_ and len(mb_) == 2 and str(mb_[0] or "Other ").startswith("Other ") and _HALF_RX.sub("", str(mb_[1] or "")) == _HALF_RX.sub("", str(src)))
            if newly and not went_out(c, v) and (not from_other or name_said(v)):
                # r69e: a half judges the companies that come to it from "Other" where its name is no test of what they sell (few of its
                # companies' words say it): the theme's own product named as what they make is (between layers: the rules before)
                continue
            # each company new to the layer says why it is there, in the change log beside its move
            here = shown(v)
            if no_words(ev(c)):
                sold[id(c)] = "no words of its own: placed by its official industry" + (f" ({plain_industry(c.get('industry'))})" if c.get("industry") else "")
                continue
            # r571 (the live R57 Semiconductors deck: Intel in "Chip equipment and subsystem suppliers", "its own words were checked to show
            # it is of" it, the check having confirmed it for another group, the map's foundry layer, before a later step moved it): a check
            # vouches only for the map layer it was asked about, so a company moved since is judged on what this layer sells
            if c.get("verified") and not c.get("moved") and not c.get("kept_member") and not c.get("held_published"):
                sold[id(c)] = f"its own words were checked to show it is of “{here}”"
                continue
            if c.get("placed_by"):
                sold[id(c)] = f"its own words say what “{here}” is" if c["placed_by"] == "by_words" else f"its official industry is what “{here}” names"
                continue
            ok = judge(c, v)
            words_ = sells_layer(v, named, sold_text(ev(c), c.get("name") or ""), None, theme_words) if ok else None
            if ok and not words_ and went_out(c, v):
                # r69e (LIVE13A-001: OSI Systems back in "Fabless chip design" a re-check after one moved it out for its words): an earlier
                # re-check's move out of this layer is undone only by words of its own that say what the layer sells, never its official
                # industry or way of earning again
                ok = False
            if ok is False and v.get("scale") in ("larger", "smaller") and not name_said(v) and names_no_kind(v) \
                    and says_theme_product(business_text(ev(c), c.get("name") or ""), theme_words) and not went_out(c, v):
                sold[id(c)] = f"its own words name the theme's own product as what it makes, and “{here}”'s name is said by few of its companies' own words"
                continue
            if ok:
                sold[id(c)] = f"its own words say it sells what “{here}” is" if words_ else \
                    f"its official industry or way of earning says it sells what “{here}” is"
            elif ok is None:
                sold[id(c)] = f"by how it earns: “{here}” names no product apart from the theme's own"
            else:
                moves.append((v, c, src))
    if sold:
        for v in named:
            v["companies"] = [{**c, "sold_by": sold[id(c)]} if id(c) in sold else c for c in v["companies"]]
    if not moves:
        return out
    rest_v = next((v for v in out if v.get("official") and v.get("basis") == "rest"), None)
    for v, c, src in moves:
        s_ = c.get("ticker")
        elsewhere = [w for w in named if w is not v and shown(w) != shown(v)]          # never the other half of the same layer
        dest = next((w for w in elsewhere if src and src in names(w) and (by_how(w) or w.get("industry_group") or judge(c, w) is not False)), None)
        if dest is None and fam(c):
            how = [w for w in elsewhere if by_how(w) and main(w["companies"]) == fam(c)]
            dest = max(how, key=lambda w: len(w["companies"])) if how else None
        if dest is None:
            dest = next((w for w in elsewhere if placed_in.get(s_) and placed_in[s_] in names(w) and not by_how(w)
                         and judge(c, w) is not False), None)
        why = (f"its own words don't say it sells what “{shown(v)}” is ({defined(v)}), nor does its official industry"
               + (f" ({plain_industry(c.get('industry'))})" if c.get("industry") else ""))
        if v.get("scale") in ("larger", "smaller") and not name_said(v) and names_no_kind(v):
            # r69e: where few of the layer's companies say its name, the test was the theme's own product: its words quoted
            from .theme_changes import first_sentence
            q_ = _quote(first_sentence(own_text(ev(c))))
            why += ", nor do its own words name the theme's own product as what it makes" + (f" (“{q_}”)" if q_ else "")
        elif went_out(c, v) and judge(c, v):
            why = (f"an earlier re-check moved it out of “{shown(v)}”, and its own words still don't say what that layer sells ({defined(v)}); "
                   "its official industry or way of earning alone doesn't bring it back")
        if dest is None and placed_in.get(s_, "") in names(v):          # the map's or the answer's own placement, nowhere to go back to
            # r582 (R58.2, the live R58.1 Consumer retail and Software decks: 1-800-Flowers, Boqii and Leslie's left out of "Single-category
            # specialty retailers", Pinterest, Snap and Reddit out of "Ad-funded consumer platforms and games", each as "another business"
            # because its words miss a word of the layer's name; most of each layer listed and left out): a company the map or the answer
            # placed here whose own words say what no other layer sells, in a line a deck can print (prints_layer), names no other business:
            # nothing contradicts its placement, so it stays here as placed, judged by how it earns. Only one whose words say what another
            # layer sells, in such a line, is listed here and left out as another business
            said_else = [w for w in elsewhere if not by_how(w) and not w.get("industry_group") and judge(c, w)
                         and prints_layer(w, own_text(ev(c)), c.get("name") or "")]
            # r64e (the live R63 Telecom US deck: Our Bond, "We provide preventative personal security powered by AI", put back into
            # "Network equipment makers", the map's old pick, once the layer it was published in was not made): a map pick whose own words,
            # official industry and name say no word of the layer's name or concept (gate_says) has its words contradicting the placement,
            # not silent on it: it goes where one with no evidence of the layer goes ("Other" when nowhere else takes it)
            # (only in a layer whose other companies' words mostly say its name: a name none of them say is the in-place rename's case,
            # truthful_layers, never a reason to empty the layer: the live R60 Cement "Regional integrated producers"; and only one read to
            # earn another way than most of the layer's other companies: a short or general description of the layer's own way of earning,
            # Alphabet's or Snap's in "Consumer internet, games and advertising", Howmet's in "Materials, castings and forgings", is silent,
            # never a contradiction)
            says_ = lambda x: gate_says(shown(v), " ".join(str(y or "") for y in (own_text(ev(x)), x.get("industry"), x.get("name"))))      # noqa: E731
            others_ = [x for x in v["companies"] if x is not c]
            apart_ = bool(fam(c)) and bool(main(others_)) and fam(c) != main(others_)
            silent_ = not said_else and (not apart_ or says_(c) is not False or sum(1 for x in others_ if says_(x)) * 2 <= len(others_))
            if silent_:
                sold[id(c)] = f"the map placed it in “{shown(v)}” and its own words say what no other layer sells"
                v["companies"] = [{**x, "sold_by": sold[id(c)]} if x is c else x for x in v["companies"]]
                continue
            if said_else:
                unfit[id(c)] = {"layer": shown(v), "why": why}
                continue
            why = (f"its own words, official industry and name say no word of “{shown(v)}” ({defined(v)}): not kept there "
                   f"on the map's pick alone")
        v["companies"] = [x for x in v["companies"] if x is not c]
        moved = {**{k: x for k, x in c.items() if k != "sold_by"}, "moved": True, "refit": {"from": shown(v), "to": shown(dest) if dest is not None else "", "why": why, "sold": True}}
        if dest is not None:
            dest["companies"].append(moved)
            continue
        if rest_v is None:
            rest_v = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
            out.append(rest_v)
        rest_v["companies"] = rest_v["companies"] + [{**moved, "fit": True}]
    if unfit:
        for v in named:
            v["companies"] = [{**c, "unfit": unfit[id(c)]} if id(c) in unfit else c for c in v["companies"]]
    return [v for v in out if v["companies"] or not v.get("by_model")]


LOST_MIN = 5                    # c54: a named layer of the previous live version with this many companies or more is never lost unsaid
GUARD_FALL = 5                  # t56: a fall of this many points or more in the share of companies in informative layers is guarded
RENAMED_SHARE = 0.5             # t56: a layer of the version before half of whose companies sit in one or two layers new to it was renamed or split


def previous_published(previous: dict, moved_before: dict | None = None, moved_out: dict | None = None, theme: str = "") -> dict:
    """t56 (R55 review): {symbol: its layer in the previous published version} read from the stored snapshot (`previous`) and, for a layer
    the snapshot already lost, the change log: a company the log moved out of a layer the snapshot no longer has, and that is still where it
    moved it, counts as of that layer. `moved_out` ({symbol: [from, to]}, theme_changes.lost_moves) holds the moves out of each such layer of
    the one re-check that removed it; without it, every logged move out of a layer the snapshot no longer has (`moved_before`).
    Live R55 Metals and Consumer retail: c54 read every logged move back, so a move INTO a restored layer ("Other" -> "Aluminium", the R54
    restore's own) put the company back in "Other" and the restored layer counted none of its companies: lost again on the next re-check."""
    prev = dict(previous or {})
    held = {_HALF_RX.sub("", str(x or "")) for x in prev.values()}
    rest = other_label(theme) if theme else ""
    for s_, mv in ((moved_out if moved_out is not None else moved_before) or {}).items():
        if not (isinstance(mv, (list, tuple)) and len(mv) >= 2 and mv[0] and mv[1]):
            continue
        frm, to = _HALF_RX.sub("", str(mv[0])), _HALF_RX.sub("", str(mv[1]))
        if frm in held or frm == rest or frm.startswith("Other "):
            continue                     # a move out of a layer the snapshot still has, or out of "Other": the snapshot says it all
        if _HALF_RX.sub("", str(prev.get(s_) or to)) == to:
            prev[s_] = frm
    return prev


def _informative(rows) -> tuple[int, int]:
    """(companies in an informative layer, companies placed) of {symbol: layer} (theme_data.layer_coverage: "Other" isn't informative)."""
    rows = {s_: _HALF_RX.sub("", str(x or "")) for s_, x in rows.items() if s_}
    return sum(1 for x in rows.values() if x and not x.startswith("Other ")), len(rows)


def _share_pts(n: int, of: int) -> int:
    return int(n * 100 / of + 0.5) if of else 0


def restore_vanished(vc: list[dict], previous: dict, evidence, theme: str, theme_words: set | None = None,
                     moved_before: dict | None = None, moved_out: dict | None = None) -> tuple[list[dict], list[dict]]:
    """(the layers with each lost layer restored, what was lost) (c54, the owner's review of the live R53 Metals deck: "Aluminium", a layer
    of 14 companies on the version before, disappeared on a re-check, 11 of its companies to "Other" and 3 to the pipe makers, informative
    coverage 51 of 66 to 41 of 66, with nothing said but "removed"): a named layer of the previous published version (previous_published:
    the snapshot, with the change log for a layer it already lost) with LOST_MIN companies or more that no layer of the re-check holds by its
    name (shown, the map's own, or one it had), and whose companies no layer new to this version took (half or more of them in one or two
    such layers: renamed or split, not lost), comes back with those of its companies that still fit it: whose own words or official
    industry say what the lost layer sells (sells_layer; a layer of one official industry: its industry), each now in "Other", or in a layer
    a later rule put it in without a recorded reason (t56, R55 review: the established category is kept until its replacement is verified:
    Manaksia Aluminium, "manufactures value-added secondary aluminium products", back from the steel pipe makers it joined on a word). A
    company stays where it is when its words were checked to show that layer's work ("verified"), a rule moved it there with its reason
    ("refit": a stage, a fallback layer, what a layer sells), the map named it there itself and its words don't contradict it, or it is in
    its own industry's group. It comes back with SPLIT_PART companies or more, else stays lost.
    Each lost layer is listed ({"layer", "before": N, "restored": n, "to": {layer: count}, "why"}) for the change log."""
    tw = kind_stems(theme) if theme_words is None else theme_words
    previous = previous_published(previous, moved_before, moved_out, theme)
    other = lambda v: bool(v.get("official")) and v.get("basis") == "rest"      # noqa: E731
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    names = lambda v: ({shown(v), v.get("was") or ""} | set(v.get("aka") or [])) - {""}      # noqa: E731
    rest_name = other_label(theme)
    held = set().union(*[names(v) for v in vc if not v.get("official")] or [set()])
    counts: dict = {}
    for s_, lay in previous.items():
        lay = _HALF_RX.sub("", str(lay or ""))
        if lay and lay != rest_name and not lay.startswith("Other "):
            counts.setdefault(lay, []).append(s_)
    lost = {lay: syms for lay, syms in counts.items() if len(syms) >= LOST_MIN and lay not in held}
    if not lost:
        return vc, []
    where = {c.get("ticker"): v for v in vc for c in v.get("companies") or []}
    named = [v for v in vc if not v.get("official") and v.get("companies")]
    out_rows, back = [], []
    taken: set = set()
    for lay, syms in sorted(lost.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        # t56: a layer whose companies went, half or more of them, to one or two layers this version has and the version before hadn't, was
        # renamed or split by the map (theme_changes' own reading of a layer event): not lost
        here = [where[s_] for s_ in syms if s_ in where]
        new = {}
        for v in here:
            if not other(v) and shown(v) not in counts:
                new[shown(v)] = new.get(shown(v), 0) + 1
        took = sorted((n for n in new.values() if n >= max(2, RENAMED_SHARE / 2 * len(syms))), reverse=True)[:2]
        if here and sum(took) >= RENAMED_SHARE * len(here):
            continue
        ghost = {"layer": lay, "description": "", "companies": []}
        fits, went, stays = [], {}, {}
        for s_ in sorted(syms):
            v = where.get(s_)
            if v is None:
                went["not in the theme now"] = went.get("not in the theme now", 0) + 1
                continue
            went[("Other" if other(v) else shown(v))] = went.get(("Other" if other(v) else shown(v)), 0) + 1
            c = next(x for x in v["companies"] if x.get("ticker") == s_)
            if s_ in taken:
                continue
            if v.get("industry_group"):
                stays["in its own industry's group"] = stays.get("in its own industry's group", 0) + 1
                continue
            ev = evidence(s_) if evidence else ""
            words = sold_text(ev, c.get("name") or "")
            mine = {**ghost, "companies": [c]}
            fit_here = sells_layer(mine, named + [mine], words, c.get("industry"), tw)
            if not other(v):
                refit = c.get("refit") if isinstance(c.get("refit"), dict) else {}
                why_stay = ("its own words were checked to show the work of the layer it is in" if c.get("verified") else
                            "a rule moved it to the layer it is in, with its reason" if refit and _HALF_RX.sub("", refit.get("to") or "") == shown(v) else
                            "the map named it in the layer it is in" if not c.get("placed") and not c.get("moved")
                            and sells_layer(v, named, words, c.get("industry"), tw) is not False else "")
                if why_stay:
                    stays[why_stay] = stays.get(why_stay, 0) + 1
                    continue
            if fit_here:
                fits.append((v, c))
            else:
                k_ = "its own words and official industry don't say what it sells"
                stays[k_] = stays.get(k_, 0) + 1
        row = {"layer": lay, "before": len(syms), "to": went}
        if stays:
            row["stayed"] = stays
        if len(fits) >= SPLIT_PART:
            ids = {id(c) for _, c in fits}
            for v in vc:
                if any(id(c) in ids for c in v.get("companies") or []):
                    v["companies"] = [c for c in v["companies"] if id(c) not in ids]
            taken |= {c.get("ticker") for _, c in fits}
            inds = {key(c.get("industry")) for _, c in fits}
            drop = ("model_out", "out_why", "unfit", "refit", "on_industry", "single", "sold_by")
            back.append({"layer": lay, "description": "", "restored": {"before": len(syms), "now": len(fits)},
                         **({"industry_group": True} if len(inds) == 1 and "" not in inds else {}),
                         "companies": [{**{k: x for k, x in c.items() if k not in drop}, "moved": True, "fit": True, "restored": lay,
                                        "sold_by": f"back in “{lay}”, a layer of the version before: its own words or official industry still say what it sells"}
                                       for _, c in fits]})
            row.update(restored=len(fits), why=f"restored: {len(fits)} of its {len(syms)} companies' own words or official industry still say "
                                                 f"what it sells")
        else:
            row.update(restored=0, why=f"none restored: {len(fits)} of its {len(syms)} companies' own words or official industry still say what "
                                       f"it sells, fewer than {SPLIT_PART}")
        if stays:            # t56: why each of its companies not back stayed where it is, the evidence-based reason recorded
            row["why"] += " (the others: " + "; ".join(f"{n_} {k_}" for k_, n_ in sorted(stays.items(), key=lambda kv: (-kv[1], kv[0]))) + ")"
        out_rows.append(row)
    if back:
        vc = [v for v in vc if v.get("companies") or not v.get("official")]
        at = next((i for i, v in enumerate(vc) if v.get("official")), len(vc))
        vc[at:at] = back
    return vc, out_rows


def share_guard(vc: list[dict], previous: dict, evidence, theme: str, theme_words: set | None = None, moved_before: dict | None = None,
                moved_out: dict | None = None) -> tuple[list[dict], dict | None]:
    """t56 (R55 review: Consumer retail 75 of 98 companies in informative layers to 69 of 98, Metals 52 of 66 to 39 of 66): when the share
    of the companies placed in informative layers falls by GUARD_FALL points or more against the previous published version
    (previous_published), each company now in "Other" whose layer there is a named layer this version still has (by its name, the map's own
    or one it had) goes back to it when its own words say what that layer sells (sells_layer; not its official industry alone: Nagpur Power,
    filed under ferro-manganese, "stopped manufacturing ferro-manganese ... now into traded mine products"), unless a recorded,
    evidence-based reason keeps it in "Other" (a rule moved it there with its reason, "refit"; no words of its own were read, "out_why",
    "unread"). The share is of the companies both versions place (the snapshot keeps those of the figures' window). (the layers, {"before":
    [n, of], "after": [n, of] (before this guard), "now": [n, of], "returned": k, "stayed": {why: count}}) when the share fell so far, else
    (the layers, None)."""
    tw = kind_stems(theme) if theme_words is None else theme_words
    prev = previous_published(previous, moved_before, moved_out, theme)
    if not prev:
        return vc, None
    other = lambda v: bool(v.get("official")) and v.get("basis") == "rest"      # noqa: E731
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    now_rows = {}
    for v in vc:
        for c in v.get("companies") or []:
            if c.get("ticker"):
                now_rows.setdefault(c["ticker"], "Other " if other(v) else shown(v) or "?")
    # the same companies on both sides: the stored snapshot holds the companies of the figures' window, the placement every company placed
    both = set(prev) & set(now_rows)
    before, after = _informative({s_: prev[s_] for s_ in both}), _informative({s_: now_rows[s_] for s_ in both})
    if not both or _share_pts(*before) - _share_pts(*after) < GUARD_FALL:
        return vc, None
    named = [v for v in vc if not v.get("official") and v.get("companies")]
    by_name: dict = {}
    for v in vc:
        if not v.get("official") or v.get("industry_group"):
            for nm in ({shown(v), v.get("was") or ""} | set(v.get("aka") or [])) - {""}:
                by_name.setdefault(nm, v)
    rest_v = next((v for v in vc if other(v)), None)
    moves, stays = [], {}
    for c in list((rest_v or {}).get("companies") or []):
        s_ = c.get("ticker")
        lay = _HALF_RX.sub("", str(prev.get(s_) or ""))
        if not lay or lay.startswith("Other "):
            continue
        dest = by_name.get(lay)
        if dest is None:
            stays["its layer of the version before is gone"] = stays.get("its layer of the version before is gone", 0) + 1
            continue
        if isinstance(c.get("refit"), dict):
            stays["a rule moved it to “Other”, with its reason"] = stays.get("a rule moved it to “Other”, with its reason", 0) + 1
            continue
        if c.get("out_why") or c.get("unread"):
            stays["no words of its own read"] = stays.get("no words of its own read", 0) + 1
            continue
        words = sold_text(evidence(s_) if evidence else "", c.get("name") or "")
        if dest.get("industry_group"):
            ok = bool(c.get("industry")) and key(c.get("industry")) == key((dest.get("companies") or [{}])[0].get("industry")) \
                and sells_layer(dest, named, words, None, tw) is not False
        else:
            ok = sells_layer(dest, named, words, None, tw) is True          # its own words: an industry label alone can be of a business it left
        if ok:
            moves.append((c, dest, lay))
        else:
            stays["its own words don't say what its layer sells"] = stays.get("its own words don't say what its layer sells", 0) + 1
    for c, dest, lay in moves:
        rest_v["companies"] = [x for x in rest_v["companies"] if x is not c]
        drop = ("model_out", "out_why", "unfit", "refit", "on_industry", "single", "sold_by", "fit")
        dest["companies"] = list(dest["companies"]) + [{**{k: x for k, x in c.items() if k not in drop}, "moved": True, "fit": True, "restored": shown(dest),
                                                        "sold_by": f"back in “{shown(dest)}”, its layer in the version before: its own words "
                                                                   f"still say what it sells"}]
    if rest_v is not None and not rest_v["companies"]:
        vc = [v for v in vc if v is not rest_v]
    now = {}
    for v in vc:
        for c in v.get("companies") or []:
            if c.get("ticker"):
                now.setdefault(c["ticker"], "Other " if other(v) else shown(v) or "?")
    return vc, {"before": list(before), "after": list(after), "now": list(_informative({s_: x for s_, x in now.items() if s_ in both})), "returned": len(moves),
                **({"stayed": stays} if stays else {})}


# ---------- p57 (R56 review): the placement contract, one set of rules every placement path goes through ----------
# The owner's review of the live R56 decks: each release's re-check under new placement rules broke companies that were right before: Capital
# One out of Payments ("its own words don't show the work of Card issuers and lenders", the same stored words the version before had checked
# to show it), Sarepta out of Biotech (one narrow layer's "no", and out of the figures with it), Duolingo moved from "Other software companies"
# into a new one-company layer "Hotels, travel and consumer services". The contract, generic for every theme:
# 1. stability: a published member keeps its theme membership and its layer through a re-check unless stronger, printed evidence moves it
#    (its own words contradict the old layer, a listing reason, a rule's printed reason): keep_published (the map check's "no" or unbacked
#    "yes"), hold_published (the last step of place_rest), theme_check.check_placements `held` (no re-ask for a member that passes);
# 2. membership apart from the layer: a layer's "no" moves a published member to its published layer or "Other", never out of the theme;
# 3. semantic fit: a layer made by a rule whose name its members' own words and industries contradict is named by what they say, or not
#    made (truthful_layers); never a new one-company layer made by a rule.
RENAME_TOP = 5                  # p57: the largest companies with words of their own a rename is read against
# r571 (the live R57 Medical devices deck: a new 2-company "Diversified groups"; the R56 audit RC1(c): no layer made with fewer than 3):
CONTRACT_SINGLE = 2             # a layer a rule made with this many companies or fewer, new to the published version, is not made


def shares_vocabulary(name: str, text: str = "", industry=None, by_property: bool = True) -> bool:
    """p57: whether a company's own words or its official industry share a word of what is made or done with a layer's name (kind_stems,
    the theme's own words counted: a software maker says "Software products and subscriptions"). A name stating no kind of business is
    shared by everyone."""
    if not name_says(name, "", set())[0]:
        return True
    if text and name_says(name, text, set(), by_property=by_property)[1]:
        return True
    if industry and not re.search(NO_ONE_BUSINESS, plain_industry(industry), re.I):
        ind = kind_stems(plain_industry(industry))
        mine = kind_stems(str(name or "").lower().replace("-", " "))
        return any(_near(a, b) for a in ind for b in mine)
    return False


def contradicted(name: str, text, industry=None, description: str = "") -> bool:
    """p57: whether a company's own words clearly contradict a layer: it has words of its own about its work, and neither they nor its
    official industry share a word of what the layer's name says (shares_vocabulary), nor of what its description says it does
    (says_of_layer). No words of its own is no evidence either way (never contradicted)."""
    words = own_text(text)
    if len(words.strip()) < 40:
        return False
    if shares_vocabulary(name, words, industry):
        return False
    if description and says_of_layer({"layer": name, "description": description}, words, set()):
        return False
    return True


def _names(v: dict) -> set[str]:
    return ({_HALF_RX.sub("", v.get("layer") or ""), v.get("was") or ""} | set(v.get("aka") or [])) - {""}


def answer_renames(kept: dict | None) -> dict:
    """p57: {map name: {"name"}} of every rename a kept answer holds: the placement's and the split's ("model_names")."""
    kept = kept if isinstance(kept, dict) else {}
    return {**((kept.get("model_names") or {}).get("rename") or {} if isinstance(kept.get("model_names"), dict) else {}),
            **(kept.get("rename") or {} if isinstance(kept.get("rename"), dict) else {})}


def published_group(layer: str, groups: list[str], rename: dict | None = None) -> str | None:
    """p57: of a map's own groups (their names as the map gave them), the one a published layer (its shown name) is: the same name, or the
    name a kept answer renamed that group to ({map name: {"name"}}, a half's "(larger)" aside). None when it is none of them."""
    shown = _HALF_RX.sub("", str(layer or ""))
    back = {}
    for k, x in (rename or {}).items():
        if isinstance(x, dict) and x.get("name"):
            back.setdefault(str(x["name"]), str(k))
    for g in groups:
        if g == shown or back.get(shown) == g:
            return g
    return None


KEPT_SAID = "kept from the published version as a member of “{layer}”: this re-check's answer alone is no evidence against a published member"


def keep_published(out: dict, published: dict, about_of=None, rename: dict | None = None, info_of=None) -> dict:
    """p57 (contract 1 and 2): the checked map (theme_check.check_placements, its groups the map's own) with each company the check left out
    of every group ("dropped") that is a published member (`published`: {symbol: its published layer}, theme_changes.published_members)
    back in the group of its published layer (published_group), else in the first group the map named it in, unless its own words contradict
    that group (contradicted): a check's "no" or unbacked "yes" alone removes no published member. Its own words' sentence that shows the
    group's work is its quote ("verified") when there is one, else it is kept unconfirmed; either way "kept_member" says why. A company the
    check moved out of a group while it stays in the theme (one of its industries) goes back the same way. `info_of(symbol)` -> the company's
    fields when the map no longer holds it ({"name", "industry", "cap"}). The placements say each kept ("kept_members")."""
    from .theme_check import group_sentence as quote_of
    pl = dict(out.get("placements") or {})
    dropped = [x for x in pl.get("dropped") or [] if isinstance(x, dict)]
    if not published or not dropped:
        return out
    vc = [dict(v, companies=list(v.get("companies") or [])) for v in out.get("value_chain") or []]
    groups = [v for v in vc if not v.get("official") and v.get("layer")]
    gnames = [v["layer"] for v in groups]
    kept, left = [], []
    for x in dropped:
        s_ = x.get("ticker")
        lay = published.get(s_)
        if not s_ or not lay:
            left.append(x)
            continue
        about = (about_of(s_) if about_of else None) or ""
        home = published_group(lay, gnames, rename)
        named = [g for g in x.get("groups") or [] if g in gnames]
        target_name = home or (named[0] if named else None)
        target = next((v for v in groups if v["layer"] == target_name), None)
        info = (info_of(s_) if info_of else None) or {}
        if target is None or (home is not None and contradicted(target_name, about, info.get("industry"), target.get("description") or "")):
            left.append(x)                   # r571: only its published group of the map's own is a test of its words (Bharat Forge)
            continue
        cur = None
        for v in vc:
            for c in v["companies"]:
                if c.get("ticker") == s_:
                    cur = (v, c)
                    break
            if cur:
                break
        if cur is not None and (not cur[0].get("official") or home is None):
            left.append(x)                   # in the theme already: in a layer of the map's (its layer the last step holds, hold_published),
            continue                         # or with no map group of its published layer: where it is
        quote = quote_of(about, f"{target['layer']} {target.get('description') or ''}") if about else ""
        said = KEPT_SAID.format(layer=_HALF_RX.sub("", str(lay)))
        if cur is not None:
            if cur[0] is target:
                continue
            cur[0]["companies"] = [c for c in cur[0]["companies"] if c is not cur[1]]
            base = {k: y for k, y in cur[1].items() if k not in ("placed", "fit", "unread", "refit", "unfit")}
        else:
            base = {"ticker": s_, "name": x.get("name") or info.get("name") or s_,
                    **({"industry": info["industry"]} if info.get("industry") else {}), **({"cap": info["cap"]} if info.get("cap") is not None else {})}
        target["companies"].append({**base, "what": quote.strip(" ,;:-–—") if quote else "", "verified": bool(quote), "kept_member": said})
        kept.append({"ticker": s_, "name": x.get("name") or s_, "layer": target["layer"], "published": _HALF_RX.sub("", str(lay)), "why": said})
    if not kept:
        return out
    vc = [v for v in vc if v.get("companies") or not v.get("official")]
    if left:
        pl["dropped"] = left
    else:
        pl.pop("dropped", None)
    pl["kept_members"] = list(pl.get("kept_members") or []) + kept
    pl["left_out"] = max(0, int(pl.get("left_out") or 0) - len(kept))
    return {**out, "value_chain": vc, "placements": pl}


HOLD_EVIDENCE = ("refit", "unfit", "placed_by", "fallback", "held", "restored")


def hold_published(vc: list[dict], published: dict, evidence, theme: str) -> tuple[list[dict], list[dict]]:
    """p57 (contract 1, the last step of place_rest): (the layers, the companies held) with each published member (`published`: {symbol: its
    published layer}) of a named layer that this placement put in "Other" or in a layer new to the published version (a move between two
    layers of the published version is the previous-layer rules', each on evidence) without a printed, evidence-based reason (HOLD_EVIDENCE: a rule's reason,
    "refit"/"unfit"; its words or industry placing it, "placed_by"; the adjacent-kind layer, "fallback"; the guards' "held"/"restored"; or its
    own words checked to show the map layer it is in, "verified" and not moved) back in its published layer when this version still has it
    (by its name, the map's own or one it had; "Other" for "Other"), unless its own words contradict that layer (contradicted). A layer a
    re-check renamed keeps its members (the same layer). Each held company says so ("held_published")."""
    if not published:
        return vc, []
    other = lambda v: bool(v.get("official")) and v.get("basis") == "rest"      # noqa: E731
    pub_names = {_HALF_RX.sub("", str(x or "")) for x in published.values()}
    by_name: dict = {}
    for v in vc:
        if not v.get("official"):
            for nm in _names(v):
                by_name.setdefault(nm, []).append(v)
    rest_v = next((v for v in vc if other(v)), None)
    moves = []
    for v in vc:
        for c in v.get("companies") or []:
            s_ = c.get("ticker")
            lay = _HALF_RX.sub("", str(published.get(s_) or ""))
            if not s_ or not lay:
                continue
            if (other(v) and lay.startswith("Other ")) or (not v.get("official") and lay in _names(v)):
                continue
            if lay.startswith("Other "):
                continue                     # out of "Other" into a named layer: more is known of it than before (truthful_layers names it)
            if v.get("official") and not other(v):
                continue                     # in its own industry's group: the map's layers hold none of it now
            if not other(v) and _names(v) & pub_names:
                continue                     # between two layers of the published version: the previous-layer rules judge it on evidence
                                             # (by_model `previous`, held_to_previous, sold_what), each move said with its reason
            ref = c.get("refit") if isinstance(c.get("refit"), dict) else None
            # (r69e: the same layer by a name it had in this placement, before a later rule renamed it, is that layer: Kanoria's move out of
            # "Regional integrated producers (smaller)", renamed "Cement integrated producers" after, is evidence against its published layer)
            same_ = {lay} | {nm for x in by_name.get(lay) or [] for nm in _names(x)}
            ref_from = _HALF_RX.sub("", str(ref.get("from") or "")) if ref is not None else ""
            if ref is not None and ref_from != lay and ref_from in same_ and not lay.startswith("Other ") and not ref.get("sold"):
                ref = None                   # (only a judgment of what it sells, sold_what's, carries over a rename)
            if ref is not None and ref_from != lay and ref_from in same_ and not lay.startswith("Other "):
                # ...only where its own words don't say what the layer sells under the name it has now ("Custom synthesis and export
                # agrochemicals" renamed "Small specialty chemicals and additives makers" for the chemical makers it holds keeps them)
                dest_ = (by_name.get(lay) or [None])[0]
                if dest_ is not None and sells_layer({"layer": lay, "description": dest_.get("description") or ""}, [],
                                                     sold_text(evidence(s_) if evidence else "", c.get("name") or ""), None, kind_stems(theme)) is not False:
                    ref = None
            if ref is not None and ref_from not in (same_ | ({other_label(theme)} if lay.startswith("Other ") else set())):
                ref = None                   # a rule's reason against another layer than its published one is no evidence against that one
            if ref is not None or any(c.get(k) for k in HOLD_EVIDENCE if k != "refit") or \
                    (c.get("verified") is True and not c.get("moved") and not v.get("official")):
                continue
            if lay.startswith("Other "):
                dest = [rest_v] if rest_v is not None else []
            else:
                dest = by_name.get(lay) or []
            if not dest or dest[0] is v:
                continue
            target = dest[0]
            if len(dest) == 2 and any(x.get("scale") for x in dest):
                big = next((x for x in dest if x.get("scale") == "larger"), dest[0])
                floor = min((x.get("cap") or 0) for x in big["companies"]) if big["companies"] else 0
                target = big if (c.get("cap") or 0) >= floor else next(x for x in dest if x is not big)
            if target is v:
                continue
            if not other(target) and contradicted(lay, evidence(s_) if evidence else "", c.get("industry"), target.get("description") or ""):
                continue
            if not other(target) and kind_bar(lay, c, evidence(s_) if evidence else "", theme)[0]:
                continue                     # e81: a kind of company that layer can never hold (kind_bar)
            moves.append((v, c, target, lay))
    rows = []
    for v, c, target, lay in moves:
        frm = other_label(theme) if other(v) else _HALF_RX.sub("", v.get("layer") or "")
        v["companies"] = [x for x in v["companies"] if x is not c]
        why = (f"kept in “{lay}”, its layer in the published version: this re-check gave no printed evidence against it (its own words "
               f"don't contradict that layer)")
        target["companies"] = list(target["companies"]) + [{**{k: x for k, x in c.items() if k not in ("moved", "single", "fit")},
                                                            "held_published": {"from": frm, "to": lay, "why": why}}]
        rows.append({"ticker": c.get("ticker"), "name": c.get("name") or c.get("ticker"), "from": frm, "to": lay})
    if rows:
        vc = [v for v in vc if v.get("companies") or not (v.get("official") or v.get("by_model"))]
    return vc, rows


# p57 (R56 audit RC2/RC3: Lilly, AbbVie, Amgen, Novo and Bristol Myers in "Specialty and clinical-stage biotechs" beside "Large pharma and
# biotech portfolios"; Fortinet in "Makers of their own products" beside "Security software subscriptions"; Unity and Clear Secure in "Cloud
# and AI compute providers"; Takeda in "Other"): a company's fit to a layer is read word by word from the layer's names, and one whose own
# words say nothing its layer's name says goes to the one existing layer whose name its words do say
_NAME_PLAIN = {"company", "companies", "provider", "providers", "maker", "makers", "supplier", "suppliers", "product", "products", "service",
               "services", "business", "businesses", "other", "own", "their", "large", "larger", "smaller", "small", "mid", "sized", "based",
               "leading", "specialty", "specialised", "specialized", "diversified", "portfolio", "portfolios", "mixed", "various", "general",
               "basic", "performance", "value", "added", "premium", "quality", "high", "major", "multinational", "american", "indian",
               "pan", "india", "regional", "national", "domestic", "integrated", "tier", "focused", "export", "listed", "established"}


def _name_words(text) -> set[str]:
    """p57: the words of a layer's name (or a company's words) that say a kind of business: lower case, a plural "s" off, no plain word
    (_NAME_PLAIN, GENERIC_FIT, _PLAIN), three letters or more ("AI" and "EPC" kept as written in upper case)."""
    out = set()
    raw = str(text or "")
    for w in re.findall(r"[A-Za-z0-9]+", _short_joined(raw.replace("-", " ")) if raw.islower() else raw.replace("-", " ")):
        lw = w.lower()
        if len(lw) < 3 and not (w.isupper() and len(w) >= 2):
            continue
        lw = lw[:-1] if lw.endswith("s") and len(lw) > 4 and not lw.endswith("ss") else lw
        if lw in _NAME_PLAIN or lw in GENERIC_FIT or lw in _PLAIN or f"{lw}s" in _NAME_PLAIN or _stem(lw) in _HOW_STEMS:
            continue
        out.add(lw)
    return out


_JOINED = ("cyber", "agro", "petro", "nano", "tele", "electro", "hydro", "geo", "aero", "thermo")      # a prefix joined to a word


def _word_near(a: str, b: str) -> bool:
    """p57: the same word, one the start of the other (five letters or more: "pharma" of "pharmaceutical"), or six first letters in common
    ("computing" and "compute"); never five alone ("enterprise" and "entertainment")."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 5 and long_.startswith(short):
        return True
    at = long_.find(short)
    if len(short) >= 6 and at > 0 and long_[:at] in _JOINED:          # "pharma" of "biopharmaceutical", "security" of "cybersecurity"
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 6


def principal_words(words) -> str:
    """p57: the sentences of a company's own words that say what it does (its principal business: theme_data.business_sentence, and the
    sentence after it), its first two sentences when none says so."""
    from .theme_data import business_sentence
    t = own_text(words)
    first = business_sentence(t)
    parts = _sentences(t)
    if first:
        i = next((k for k, x in enumerate(parts) if first[:40] in " ".join(x.split())), None)
        return " ".join([first] + ([parts[i + 1]] if i is not None and i + 1 < len(parts) else []))
    return " ".join(parts[:2])


def name_fit(v: dict, words: str, theme_words: set, every: bool = True) -> list[str]:
    """p57: the words of a layer's names (shown, the map's own and, with `every`, each earlier one; a half's "(larger)" aside) that a
    company's own words say, the theme's own words left out (every company of the theme says them)."""
    mine = _name_words(own_text(words).lower())
    said = []
    names = _names(v) if every else ({_HALF_RX.sub("", v.get("layer") or ""), v.get("was") or ""} - {""})
    for nm in names:
        for w in _name_words(nm.lower()):
            if _stem(w) in theme_words or w in said:
                continue
            if any(_word_near(a, w) for a in mine if _stem(a) not in theme_words):      # its theme word says no layer ("chemical" of "agrochemical")
                said.append(w)
    return said


# words a layer's name may carry that say no kind of business apart (a "systems" or "devices" of any layer): never where a company goes
_TARGET_FILLER = {"system", "device", "processing", "digital", "data", "network", "integrated", "technology", "equipment", "component",
                  "part", "consumer", "commercial", "online", "platform", "mixed", "multi", "home", "care", "owner", "contract", "design",
                  "engineering", "research", "test", "testing", "development", "subscription", "licence", "license", "licensing", "software",
                  "service", "manufacturing", "producer"}
# what a company says it is ("an American multinational pharmaceutical company"): one word of a layer's name said there is enough
_SELF = re.compile(r"\b(?:is|are|as)\s+(?:an?|the|one of the)\s+([^.;:]{0,90}?)\b(?:company|companies|corporation|firm|group|maker|makers|"
                   r"manufacturer|producer|provider|developer|business|bank|lender|insurer|operator|platform)\b", re.I)


def self_words(words) -> set[str]:
    """p57: the words a company's own words call it by ("is an American multinational pharmaceutical company": pharmaceutical)."""
    out = set()
    for m_ in _SELF.finditer(own_text(words)):
        out |= _name_words(m_.group(1).lower())
    return out


LAYER_FIT_SHARE = 0.5            # p57 (R56 audit RC2): a layer of which fewer of the companies with words of their own say its name is a catch-all


def desc_fit(v: dict, words: str, theme_words: set) -> list[str]:
    """p57: the words of what a layer's description says its companies make or do (says_of_layer's reading: the customers it names and
    what it says they are not left out) that a company's own words say."""
    lay = whole_stems(_CONTRAST.sub(" ", _CUSTOMERS.sub(" ", str(v.get("description") or "")))) - theme_words - _FIT_STOP
    mine = whole_stems(own_text(words)) - theme_words - _FIT_STOP
    return sorted(b for b in lay if len(b) >= 4 and any(_near(a, b) for a in mine))


CONTRADICTED_SHARE = 0.25       # p57: a layer's name is contradicted when fewer than this share of its companies with words say its own words
FIT_ASK_MAX = 40                # p57: flagged companies one answer a theme judges, the largest first
_BASED = re.compile(r"\b[a-z0-9]+-(?:based|enabled|powered|driven|native|first)\b", re.I)      # "cloud-based software": how, not what it is
_CONGLOMERATE = re.compile(r"\bconglomerate\b|\bdiversified (?:group|company|industrial|technology)\b|\boperat\w* in the fields of\b", re.I)


def _fit_text(text) -> str:
    """p57: a company's own words for the fit test, a "<word>-based" kind of delivery left out ("cloud-based restaurant software")."""
    return _CUSTOMERS.sub(" ", _BASED.sub(" ", own_text(text)))          # the customers it names are not what it does


def distinct_words(v: dict, layers: list[dict], theme_words: set) -> set[str]:
    """p57: the words of a layer's name (shown and the map's own) that say a kind of business no other layer's name says, the theme's own
    words left out ("robotic" of "Surgical robotics systems" beside "Orthopedic and surgical device makers")."""
    nm = lambda x: {_HALF_RX.sub("", x.get("layer") or ""), x.get("was") or ""} - {""}      # noqa: E731
    mine = {w for n in nm(v) for w in _name_words(n.lower()) if _stem(w) not in theme_words and w not in _TARGET_FILLER}      # r571: never "system"
    others = {w for x in layers if x is not v and _HALF_RX.sub("", x.get("layer") or "") != _HALF_RX.sub("", v.get("layer") or "")
              for n in nm(x) for w in _name_words(n.lower())}
    return {w for w in mine if not any(_word_near(w, o) for o in others)}


def fits_layer(v: dict, text, industry, theme_words: set) -> list[str]:
    """p57: the vocabulary test: the words of a layer's names (no filler word) a company's own words say, or its official industry's."""
    said = [w for w in name_fit(v, _fit_text(text), theme_words, every=False) if w not in _TARGET_FILLER]
    if not said and industry and not re.search(NO_ONE_BUSINESS, plain_industry(industry), re.I):
        said = [w for w in name_fit(v, plain_industry(industry), theme_words, every=False) if w not in _TARGET_FILLER]
    return said


def shares_layer(v: dict, text, industry) -> bool:
    """p57: whether a company's own words or official industry share any word of its layer's names (every name it had; the theme's own
    words and the plain words of a name counted: "hospital", "component"): the strict test's "shares no vocabulary" read loosely."""
    words = _name_words(_CUSTOMERS.sub(" ", _fit_text(text)).lower()) | (_name_words(plain_industry(industry).lower()) if industry else set())
    return any(_word_near(a, w) for nm in _names(v) for w in _name_words(nm.lower()) | _fit_words(nm) for a in words)


def clearly_fits(v: dict, text, theme_words: set) -> list[str]:
    """p57: the words of an existing layer's name its principal sentences clearly say: two of them, or one it calls itself by ("an
    American multinational pharmaceutical company"), or one long distinctive word of its first sentence."""
    first = principal_words(_fit_text(text))
    said = [w for w in name_fit(v, first, theme_words, every=False) if w not in _TARGET_FILLER]
    if len(said) >= 2:
        return said
    if len(said) == 1 and (any(_word_near(a, said[0]) for a in self_words(text)) or
                           (len(said[0]) >= 9 and name_fit(v, (_sentences(own_text(text)) or [""])[0], theme_words, every=False))):
        return said
    return []


def flag_misfits(vc: list[dict], words_of, theme: str) -> list[dict]:
    """p57 (R56 audit RC2, second wave): the strict test. A company with words of its own is flagged when
    1. its own words and official industry share no word with its layer's name (fits_layer), and its principal sentences clearly say an
       existing other layer's (clearly_fits), or it is in "Other" and they do; or
    2. its layer's own name is contradicted by most of its companies (fewer than LAYER_FIT_SHARE of those with words say a word only its
       name says, distinct_words: "Surgical robotics systems" whose companies make no robots) and it says none of those words.
    A company a rule placed with its printed reason, or kept from the published version, is never flagged. [{"symbol", "name", "layer",
    "why": "fits another" | "name contradicted", "targets": [layer names], "words"}], the largest first."""
    tw = kind_stems(theme)
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    named = [v for v in vc if not v.get("official") and v.get("companies")]
    groups: dict = {}
    for v in named:
        groups.setdefault(shown(v), []).append(v)
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    words = lambda c: (words_of(c.get("ticker")) if words_of else None) or c.get("what") or ""      # noqa: E731
    contradicted, catch_all = {}, set()
    for nm, vs in groups.items():
        dw = distinct_words(vs[0], named, tw)
        worded = [c for x in vs for c in x["companies"] if len(own_text(words(c)).strip()) >= 40]
        says = lambda c: any(_word_near(a, w) for a in _name_words(_fit_text(words(c)).lower()) for w in dw)      # noqa: E731
        if dw and len(worded) >= 3 and sum(1 for c in worded if says(c)) < CONTRADICTED_SHARE * len(worded):
            contradicted[nm] = (dw, says)
        if worded and sum(1 for c in worded if name_fit(vs[0], words(c), tw)) < LAYER_FIT_SHARE * len(worded):
            catch_all.add(nm)
    out = []
    for v in named + ([rest_v] if rest_v is not None else []):
        here = shown(v) if v is not rest_v else ""
        for c in v["companies"]:
            text = words(c)
            if len(own_text(text).strip()) < 40 or isinstance(c.get("refit"), dict) or c.get("fallback") or c.get("kept_member") \
                    or c.get("held_published") or (v is rest_v and (c.get("unread") or c.get("out_why"))):
                continue
            plain = _CUSTOMERS.sub(" ", own_text(text))          # the customers it names are not what it does ("for passenger vehicles")
            # never into a layer whose own name its companies contradict, nor a catch-all most of whose companies don't say its name
            targets = [nm for nm, vs in groups.items() if nm != here and nm not in contradicted and nm not in catch_all
                       and clearly_fits(vs[0], plain, tw)]
            if here in contradicted and not contradicted[here][1](c):
                targets = [t for t in targets if len(clearly_fits(groups[t][0], plain, tw)) >= 2]
                if targets:
                    out.append({"c": c, "why": "name contradicted", "targets": targets})
            elif targets and (v is rest_v or not shares_layer(v, text, c.get("industry"))):
                out.append({"c": c, "why": "fits another", "targets": targets})
    out.sort(key=lambda x: (-(x["c"].get("cap") or 0), x["c"].get("ticker") or ""))
    return [{"symbol": x["c"].get("ticker"), "name": x["c"].get("name") or x["c"].get("ticker"), "why": x["why"], "targets": x["targets"],
             "layer": next((("" if v is rest_v else shown(v)) for v in named + ([rest_v] if rest_v else []) if x["c"] in v["companies"]), ""),
             "words": own_text(words(x["c"]))} for x in out]


def vocabulary_choice(flagged: list[dict], vc: list[dict], words_of, theme: str) -> dict:
    """p57: the vocabulary test's own answer for flagged companies ({symbol: existing layer name, or "" for "Other"}): the one target whose
    name its principal sentences say the most of (a tie answers nothing), else "Other" for a company whose layer's name is contradicted.
    It stands in for the model only in offline replays (the release gate, the tests); the live placement asks the model
    (theme_check.best_existing_layers) and checks its answer with the same test."""
    tw = kind_stems(theme)
    by = {}
    for v in vc:
        if not v.get("official") and v.get("companies"):
            by.setdefault(_HALF_RX.sub("", v.get("layer") or ""), v)
    out = {}
    for f in flagged:
        text = (words_of(f["symbol"]) if words_of else None) or f.get("words") or ""
        def score(t):                    # the words of its name said, then the share of its name they are ("Aluminium" over "Aluminium
            said = len(clearly_fits(by[t], text, tw))           # and copper mining and smelting" for an aluminium maker)
            of = len({w for w in _name_words(t.lower()) if _stem(w) not in tw}) or 1
            return (said, round(said / of, 3)) if said else (0, 0)
        scores = {t: score(t) for t in f.get("targets") or [] if t in by}
        top = max(scores.values(), default=(0, 0))
        best = [t for t, n in scores.items() if n == top and n[0]]
        if len(best) == 1:
            out[f["symbol"]] = best[0]

    return out


def misfit_moves(vc: list[dict], evidence, theme: str, words_of=None, ask=None, kept_fit: dict | None = None
                 ) -> tuple[list[dict], list[dict], dict | None]:
    """p57 (R56 audit RC2/RC3, second wave; contract 3): (the layers, the moves, the answer to keep). The strict test flags misfits
    (flag_misfits); for those only, one answer a theme and rules version (`kept_fit` {"rules", "moves"} when this version already has one;
    else `ask`, theme_check.best_existing_layers, at most FIT_ASK_MAX companies, the largest first) names the best existing layer or "Other".
    An answer is taken only when it passes the same vocabulary test (fits_layer on the company's own words or official industry; "Other"
    for a flagged company), never into a layer of another stage; anything else keeps the published placement. No layer is made."""
    from .theme_check import best_existing_layers
    flagged = flag_misfits(vc, words_of, theme)
    answer = None
    if isinstance(kept_fit, dict) and kept_fit.get("rules") == RULES:
        moves, answer = dict(kept_fit.get("moves") or {}), kept_fit
    elif ask is not None and flagged:
        layers = []
        for v in vc:
            if not v.get("official") and v.get("companies") and _HALF_RX.sub("", v.get("layer") or "") not in [x["layer"] for x in layers]:
                layers.append({"layer": _HALF_RX.sub("", v.get("layer") or ""), "description": v.get("description") or ""})
        try:
            moves = best_existing_layers(layers, flagged[:FIT_ASK_MAX], ask, theme)
        except Exception as e:           # the AI busy or no answer: nothing moves; asked again on a later check
            print("theme base: misfits not asked:", theme[:40], type(e).__name__, str(e)[:100])
            return vc, [], None
        answer = {"rules": RULES, "moves": moves}
    else:
        return vc, [], None
    tw = kind_stems(theme)
    flag = {f["symbol"]: f for f in flagged}
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    groups: dict = {}
    for v in vc:
        if not v.get("official") and v.get("companies"):
            groups.setdefault(shown(v), []).append(v)
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    rows = []
    sizes = {id(v): len(v.get("companies") or []) for v in vc}
    for s_, to in moves.items():
        f = flag.get(s_)
        if f is None:
            continue                         # no longer a misfit by the strict test: where it is
        cur = next(((v, c) for v in vc for c in v.get("companies") or [] if c.get("ticker") == s_), None)
        if cur is None:
            continue
        v, c = cur
        if v is not rest_v and sizes[id(v)] <= 2:
            continue                         # never a layer left with one company by a move out of it
        text = (words_of(s_) if words_of else None) or c.get("what") or ""
        frm = "" if v is rest_v else shown(v)
        if frm and names_core(text, v, theme):
            continue                         # third wave: its principal sentences name its present layer's work: a stable placement
        if to:
            dest_vs = groups.get(to)
            if not dest_vs or to == frm:
                continue
            said = fits_layer(dest_vs[0], text, c.get("industry"), tw)
            if frm:                          # a word its present layer's name says too places it nowhere new
                here_w = {w for n in _names(v) for w in _name_words(n.lower())}
                said = [w for w in said if not any(_word_near(w, h) for h in here_w)]
            st = layer_stage(dest_vs[0])
            if not said or (st and company_stage(own_text(text))[0] not in ("", st)):
                continue                     # the answer isn't borne out by its own words: the published placement stays
            target = dest_vs[0]
            if len(dest_vs) == 2:
                big = next((x for x in dest_vs if x.get("scale") == "larger"), dest_vs[0])
                floor = min((x.get("cap") or 0) for x in big["companies"]) if big["companies"] else 0
                target = big if (c.get("cap") or 0) >= floor else next(x for x in dest_vs if x is not big)
            why = (f"its own words say “{'”, “'.join(said)}” of “{to}”" + (f", nothing “{frm}” names" if f["why"] == "fits another" and frm else
                   f"; few of “{frm}”'s companies say what its name says, and it doesn't" if frm else "") + " (the placement contract)")
        else:
            if v is rest_v or f["why"] != "fits another" or shares_layer(v, text, c.get("industry")) or len(desc_fit(v, text, tw)) > 1:
                continue                     # "Other" only for one whose words share nothing with its layer's names or definition
            if rest_v is None:
                rest_v = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                vc = vc + [rest_v]
            target, said = rest_v, []
            why = (f"its own words say nothing of what “{frm}” names, nor of any other layer's work"
                   if f["why"] == "fits another" else f"few of “{frm}”'s companies say what its name says, and its own words don't") + \
                " (the placement contract)"
        v["companies"] = [x for x in v["companies"] if x is not c]
        sizes[id(v)] -= 1
        target["companies"] = list(target["companies"]) + [{**{k: x for k, x in c.items() if k not in ("single", "unfit", "unfit_why", "sold_by")},
                                                            "moved": True, **({"fit": True} if to else {}),
                                                            "refit": {"from": frm or other_label(theme), "to": to, "why": why, "words": said}}]
        rows.append({"ticker": s_, "name": c.get("name") or s_, "from": frm or "Other", "to": to or "Other", "said": said, "flag": f["why"]})
    if rows:
        vc = [v for v in vc if v.get("companies") or not (v.get("by_model") or v.get("by_place") or v.get("industry_group") or v.get("official"))]
    return vc, rows, answer


_CORE_STOP = {"and", "the", "for", "with", "other", "company", "companies", "maker", "makers", "producer", "producers", "provider", "providers",
              "supplier", "suppliers", "product", "products", "service", "services", "business", "businesses", "regional", "integrated", "large",
              "larger", "smaller", "small", "mid", "sized", "pan", "india", "specialty", "diversified", "leading", "mixed", "general", "focused",
              "based", "their", "own", "group", "groups", "operator", "operators", "manufacturing", "manufacturers", "manufacturer",
              "platform", "platforms", "solution", "solutions", "system", "systems", "technology", "technologies"}


def core_words(v: dict, theme: str) -> set[str]:
    """p57 (third wave): the words of what a layer's name says its companies do (shown name and the map's own; plain and scale words out),
    or the theme's own words when it names nothing beyond them ("Regional integrated producers" of Cement: cement)."""
    out = set()
    for n in {_HALF_RX.sub("", v.get("layer") or ""), v.get("was") or ""} - {""}:
        for w in re.findall(r"[a-z]+", n.lower().replace("-", " ")):
            w = w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith("ss") else w
            if len(w) >= 4 and w not in _CORE_STOP and f"{w}s" not in _CORE_STOP:
                out.add(w)
    tw = {w[:-1] if w.endswith("s") and len(w) > 4 else w for w in re.findall(r"[a-z]+", str(theme).lower()) if len(w) >= 4 and w not in _CORE_STOP}
    return out or tw


def names_core(text, v: dict, theme: str) -> list[str]:
    """p57 (third wave): the core words of a company's present layer (core_words) its principal sentences say: a stable placement (a cement
    maker in a cement layer, a developer among the developers) no answer moves."""
    mine = {(w[:-1] if w.endswith("s") and len(w) > 4 else w) for w in re.findall(r"[a-z]+", principal_words(_fit_text(text)).lower())}
    core = core_words(v, theme)
    said = sorted(w for w in core if any(_word_near(a, w) for a in mine))
    # r60 (R60, the owner's review of the live R59 Consumer retail deck: MINISO, "a Chinese retailer and variety store chain", moved from
    # "Off-price, dollar and value retailers" to "Apparel and consumer brand owners"): principal words that say the layer's concept
    # (concept_said: "variety store chain" of value retail) are a stable placement too
    hit = concept_said(_HALF_RX.sub("", v.get("layer") or ""), principal_words(_fit_text(text)), v.get("description") or "")
    if hit:
        return sorted(set(said) | {hit.group(0).lower()})
    return said if len(said) * 2 >= len(core) else []          # half its core or more ("cloud" alone of "cloud ... compute ... infrastructure": no)


def verbatim(quote: str, text: str) -> bool:
    """p57 (third wave): a quote of at least four words found word for word in a company's stored words (case and punctuation aside)."""
    from .theme_check import norm
    q = norm(quote)
    return len(q.split()) >= 4 and f" {q} " in f" {norm(text)} "


def audit_moves(vc: list[dict], evidence, theme: str, words_of=None, ask=None, kept_audit: dict | None = None
                ) -> tuple[list[dict], list[dict], dict | None]:
    """p57 (third wave; the R56 audit's RC2 P0s, which shared words can't separate): (the layers, the moves, the answer to keep). One model
    answer a theme and rules version (`kept_audit` {"rules", "moves"} when kept; else `ask`, theme_check.audit_layers) audits the named
    layers' largest AUDIT_MAX members: which don't do what their layer says, and each one's best existing layer or "Other", with a quote for
    the new layer and one against the old. A move is taken only when both quotes are word for word in its stored words (description,
    segments, filings), the new quote says a word of the new layer's name or definition, the old quote says nothing of the old layer's core
    and its principal sentences don't name the old layer's core activity (a stable placement: names_core); never into a layer of another
    stage, never leaving a layer with one company. Anything else keeps the published placement. No layer is made."""
    from .theme_check import AUDIT_MAX, audit_layers
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    words = lambda c: (words_of(c.get("ticker")) if words_of else None) or c.get("what") or ""      # noqa: E731
    stored = lambda c: " ".join(x for x in (words(c), evidence(c.get("ticker")) if evidence else "") if x)      # noqa: E731
    groups: dict = {}
    for v in vc:
        if not v.get("official") and v.get("companies"):
            groups.setdefault(shown(v), []).append(v)
    answer = None
    if isinstance(kept_audit, dict) and kept_audit.get("rules") == RULES:
        moves, answer = dict(kept_audit.get("moves") or {}), kept_audit
    elif ask is not None and groups:
        every = sorted(((c, nm) for nm, vs in groups.items() for x in vs for c in x["companies"] if len(own_text(words(c)).strip()) >= 40
                        and not isinstance(c.get("refit"), dict)),
                       key=lambda t: (-(t[0].get("cap") or 0), t[0].get("ticker") or ""))[:AUDIT_MAX]
        layers = [{"layer": nm, "description": vs[0].get("description") or "",
                   "members": [{"symbol": c.get("ticker"), "name": c.get("name"), "words": own_text(words(c))} for c, n in every if n == nm]}
                  for nm, vs in groups.items()]
        layers = [x for x in layers if x["members"]] + [{"layer": nm, "description": vs[0].get("description") or "", "members": []}
                                                        for nm, vs in groups.items() if not any(c for c, n in every if n == nm)]
        try:
            moves = audit_layers(layers, ask, theme)
        except Exception as e:           # the AI busy or no answer: nothing moves; asked again on a later check
            print("theme base: layers not audited:", theme[:40], type(e).__name__, str(e)[:100])
            return vc, [], None
        answer = {"rules": RULES, "moves": moves}
    else:
        return vc, [], None
    tw = kind_stems(theme)
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    sizes = {id(v): len(v.get("companies") or []) for v in vc}
    rows = []
    # r60 (LIVE9A-006, the live R59 Oil and gas (IN) page: Reliance Industries, the theme's largest company, sent to "Other oil and gas
    # companies" on an audit quote about the retail subsidiaries it holds): one of the theme's largest (TOP_MEMBERS, never more than its
    # largest quarter) is never taken out of every layer on one answer's quote; it stays where it is placed
    caps_ = sorted(((c.get("cap") or 0, c.get("ticker")) for v in vc for c in v.get("companies") or [] if c.get("ticker")), key=lambda t: (-t[0], t[1]))
    top_ = {t for cap, t in caps_[:min(TOP_MEMBERS, len(caps_) // TOP_SHARE)] if cap}
    for s_, x in moves.items():
        cur = next(((v, c) for v in vc if not v.get("official") for c in v.get("companies") or [] if c.get("ticker") == s_), None)
        if cur is None or not isinstance(x, dict):
            continue
        v, c = cur
        to, qn, qo = x.get("to") or "", x.get("quote_new") or "", x.get("quote_old") or ""
        text = stored(c)
        core = core_words(v, theme)
        qo_core = [w for w in core if any(_word_near(a, w) for a in re.findall(r"[a-z]+", qo.lower()))]
        # r571 (the live R57 Software audit: Twilio's "an American cloud communications company" refused on "cloud" alone, one of its layer's
        # three core words): the old quote is read by the same measure as a stable placement, half the core or more
        if not verbatim(qo, text) or names_core(words(c), v, theme) or (qo_core and len(qo_core) * 2 >= len(core)):
            continue                         # a quote not in its words, or its own words name its present layer's work: it stays
        # e79 (LIVE15A-004/008: Essex Property Trust moved to "Other" on "Essex has elected to be treated as a REIT for federal income tax
        # purposes ..."): a sentence of how a company is held or taxed says nothing of what it owns or does, so it is no evidence against a layer
        if structure_quote(qo):
            continue
        # r69e (the live R67 Hotels deck: TBO Tek moved out of "Platforms and marketplaces" on its words "operating multiple online technology
        # platforms", the reason printing them as "not what “Platforms and marketplaces” names"): a quote that says a word of its present
        # layer's own name, as written, is no evidence against that layer, whatever word any company may use
        said_name = [w for w in re.findall(r"[a-z]+", shown(v).lower()) if len(w) >= 4 and w not in _JOINING]
        if any(_word_near(a, w) for w in said_name for a in re.findall(r"[a-z]+", qo.lower())):
            continue
        if sizes[id(v)] <= 2 or to == shown(v):
            continue
        if to:
            dest_vs = groups.get(to)
            if not dest_vs or not verbatim(qn, text):
                continue
            said = [w for w in name_fit(dest_vs[0], qn, tw, every=False) if w not in _TARGET_FILLER] or \
                desc_fit(dest_vs[0], qn, tw)
            st = layer_stage(dest_vs[0])
            if not said or (st and company_stage(own_text(words(c)))[0] not in ("", st)):
                continue
            target = dest_vs[0]
            if len(dest_vs) == 2:
                big = next((y for y in dest_vs if y.get("scale") == "larger"), dest_vs[0])
                floor = min((y.get("cap") or 0) for y in big["companies"]) if big["companies"] else 0
                target = big if (c.get("cap") or 0) >= floor else next(y for y in dest_vs if y is not big)
            why = (f"its own words: “{qn}” (what “{to}” is), and “{qo}”, not what “{shown(v)}” names (the placement contract's audit)")
        else:
            if shares_layer(v, words(c), c.get("industry")) or s_ in top_:
                continue                     # "Other" only for one whose words share nothing with its layer, never one of the largest
            if rest_v is None:
                rest_v = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                vc = vc + [rest_v]
                sizes[id(rest_v)] = 0
            target, said = rest_v, []
            why = f"its own words: “{qo}”, not what “{shown(v)}” names, nor any other layer's work (the placement contract's audit)"
        v["companies"] = [y for y in v["companies"] if y is not c]
        sizes[id(v)] -= 1
        target["companies"] = list(target["companies"]) + [{**{k: y for k, y in c.items() if k not in ("single", "unfit", "unfit_why", "sold_by")},
                                                            "moved": True, **({"fit": True} if to else {}),
                                                            "refit": {"from": shown(v), "to": to, "why": why, "quotes": [qn, qo]}}]
        rows.append({"ticker": s_, "name": c.get("name") or s_, "from": shown(v), "to": to or "Other", "quote_new": qn, "quote_old": qo})
    if rows:
        vc = [v for v in vc if v.get("companies") or not (v.get("by_model") or v.get("by_place") or v.get("industry_group") or v.get("official"))]
    return vc, rows, answer


_FIELDS = re.compile(r"\b(?:in the fields of|operat\w* (?:in|across)|active in|businesses (?:in|span\w*|include)|segments? (?:are|include|of))\b", re.I)
SCALE_LAYER = r"\b(?:large|largest|major|big|global|leading)\b"          # r571: a layer named by scale ("Large pharma and biotech portfolios")
NICHE_LAYER = r"clinical|\bstage\b|specialty|specialised|specialized|emerging|\bsmall|niche|early|pipeline|developers?\b"


def scale_moves(vc: list[dict], words_of, theme: str, figures_of) -> tuple[list[dict], list[dict]]:
    """r571 (the R56 audit BIO-2, still on the live R57 Biotech deck: Novo Nordisk, AbbVie, Amgen and Bristol Myers in "Specialty and
    clinical-stage biotechs" beside "Large pharma and biotech portfolios"; the model's audit named none of them): where a theme has a layer
    named by scale, a company of a sibling layer named by a stage or a niche joins it when (a) its stored revenue is at or above the median
    revenue of the scale layer's companies, (b) it is commercial: not a development-stage company by its own words (company_stage), and its
    own words name products on sale or it has an operating profit, and (c) its own words or official industry say a word of the scale layer's
    name (a word inside a longer one counts: "pharma" of "biopharmaceutical"). (the layers, the moves). Its reason printed ("refit")."""
    import statistics
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    named = [v for v in vc if not v.get("official") and v.get("companies")]
    scale = {}
    for v in named:
        if re.search(SCALE_LAYER, f"{shown(v)} {v.get('was') or ''}", re.I) and not re.search(NICHE_LAYER, shown(v), re.I):
            scale.setdefault(shown(v), []).append(v)
    if not scale or figures_of is None:
        return vc, []
    rows = []
    for nm, svs in scale.items():
        revs = [r for x in svs for c in x["companies"] for r in [(figures_of(c.get("ticker")) or {}).get("revenue")] if r]
        if len(revs) < 3:
            continue
        median = statistics.median(revs)
        words = {w for w in re.findall(r"[a-z]+", f"{nm} {svs[0].get('was') or ''}".lower()) if len(w) >= 5}
        words -= {"large", "largest", "major", "global", "leading", "portfolio", "portfolios", "companies", "makers", "producers"}
        target = svs[0]
        for v in named:
            if shown(v) == nm or not re.search(NICHE_LAYER, f"{shown(v)} {v.get('was') or ''}", re.I) or len(v["companies"]) <= 2:
                continue
            for c in list(v["companies"]):
                f = figures_of(c.get("ticker")) or {}
                rev, ebitda = f.get("revenue"), f.get("ebitda")
                text = own_text(words_of(c.get("ticker")) or c.get("what") or "")
                if not rev or rev < median or len(text.strip()) < 40:
                    continue
                stage, said = company_stage(text, rev, ebitda)
                if stage == "development" or not (stage == "commercial" or (ebitda or 0) > 0):
                    continue
                mine = set(re.findall(r"[a-z]+", f"{text} {plain_industry(c.get('industry') or '')}".lower()))
                hit = sorted(w for w in words if any(w in a for a in mine))
                if not hit or len(v["companies"]) <= 2:
                    continue
                how = said if stage == "commercial" and said.startswith("its own words") else f"an operating profit (EBITDA margin {ebitda:.1f}%)"
                why = (f"revenue of ${rev / 1000:.1f} bn, at or above the median of “{nm}” (${median / 1000:.1f} bn); a commercial company: {how}; "
                       f"its own words or industry say “{'”, “'.join(hit)}” (the placement contract)")
                v["companies"] = [x for x in v["companies"] if x is not c]
                target["companies"] = list(target["companies"]) + [{**{k: x for k, x in c.items() if k not in ("sold_by", "unfit", "unfit_why")},
                                                                    "moved": True, "fit": True, "refit": {"from": shown(v), "to": nm, "why": why, "scale": True}}]
                rows.append({"ticker": c.get("ticker"), "name": c.get("name") or c.get("ticker"), "from": shown(v), "to": nm, "revenue": rev,
                             "median": median})
    return vc, rows


_WHOLE_PLAIN = {"care", "consumer", "health", "safety", "industrial", "services", "service", "solution", "solutions", "goods", "material"}


# r572 round 2 (the live R57.1 Software deck: Shopify, "a cloud e-commerce management platform", and Twilio, "a cloud communications
# company ... programmable communication tools", in "Cloud and AI compute providers"): a layer whose name says its companies sell computing
# or infrastructure (never one named by software), and the words that say a company sells it. "Cloud" or "cloud-based" said of another
# product ("cloud e-commerce platform", "cloud-based restaurant software", "cloud communications") is a word about that product
COMPUTE_LAYER = r"\bcomput(?:e|ing)\b|\bhosting\b|data cent(?:er|re)s?|\bcapacity\b|cloud infrastructure|infrastructure providers?"
COMPUTE_SAYS = (r"\bcomput(?:e|ing)\b|\bcapacity\b|\bhosting\b|data cent(?:er|re)s?|\bgpus?\b|infrastructure[- ]as[- ]a[- ]service|\biaas\b|"
                r"\bservers?\b|colocation|\b(?:ai|cloud|it|computing|digital) infrastructure\b|hyperscale")
CLOUD_ADJECTIVE = r"\bcloud(?:[- ]based|[- ]native)?\s+(?!comput\w*|infrastructure|hosting|servers?|capacity|data cent\w*)"


def says_compute(text: str) -> bool:
    """r572: whether a company's own words say it sells computing, capacity, hosting or data centres ("cloud" said of another product aside)."""
    return bool(re.search(COMPUTE_SAYS, re.sub(CLOUD_ADJECTIVE, " ", str(text or ""), flags=re.I), re.I))


def unsaid_moves(vc: list[dict], words_of, theme: str, published: dict | None = None) -> tuple[list[dict], list[dict]]:
    """r572 round 2 (the release gate on the live R57.1 IT services input: Riddhi Corporate Services, "document management, inbound and
    outbound contact centre, data entry", moved by how it earns into "Engineering R&D services"): a company the split moved into a named layer
    by how it earns, new to it against the published version, whose own words, official industry and name say no word of that layer's names
    (says_name), goes to the theme's "Other"
    group with the reason printed: a way of earning shared is no evidence of what a layer is. (the layers, a row for each company moved)."""
    rows = []
    rest = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    for v in vc:
        if v.get("official") or not v.get("layer") or v.get("by_model") or v.get("by_place") or v.get("industry_group"):
            continue
        names = [n for n in dict.fromkeys([_HALF_RX.sub("", v["layer"]), v.get("was") or ""] + list(v.get("aka") or [])) if n]
        keep = []
        for c in v.get("companies") or []:
            text = " ".join(str(x or "") for x in ((words_of(c.get("ticker")) if words_of else None), c.get("what"), c.get("industry"), c.get("name")))
            was_ = _HALF_RX.sub("", str((published or {}).get(c.get("ticker")) or ""))
            if not c.get("moved") or isinstance(c.get("refit"), dict) or not own_text(text).strip() or was_ in names \
                    or any(says_name(n, [text]) is not False for n in names):
                keep.append(c)
                continue
            if rest is None:
                rest = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                vc = vc + [rest]
            shown = _HALF_RX.sub("", v["layer"])
            why = f"moved by how it earns into “{shown}”, whose name its own words, official industry and name say no word of"
            rest["companies"] = list(rest.get("companies") or []) + [{**c, "refit": {"from": shown, "to": _HALF_RX.sub("", rest["layer"]), "why": why}}]
            rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": shown, "to": rest["layer"], "why": why})
        v["companies"] = keep
    if not rows:
        return vc, []
    return [v for v in vc if v.get("companies") or v.get("official") or not (v.get("by_model") or v.get("scale"))], rows


COMPUTE_THEME = r"\bcomput|\bdata\b|\bcloud|\bhosting|\bnetwork|\btelecom|\binternet|\bsoftware|\bdigital|\btechnolog|\bsemiconductor|\bit\b"


def off_theme_compute(vc: list[dict], theme: str) -> tuple[list[dict], list[dict]]:
    """r58 (R58, the owner's open items on the live R57.2 decks: a "Data centres, hosting and networks" layer in the US oil and gas theme): a
    layer made by how its companies earn (by_model) whose name says computing or capacity (COMPUTE_LAYER), in a theme whose own name and map
    layers say nothing of computing, data or networks (COMPUTE_THEME), is not made: its companies are in the theme by their own industry, and
    go to its "Other" group, each with the reason. (the layers, a row for each company moved)."""
    named_words = " ".join([str(theme)] + [_HALF_RX.sub("", v.get("layer") or "") for v in vc if not v.get("official") and not v.get("by_model")])
    if re.search(COMPUTE_THEME, named_words, re.I):
        return vc, []
    rows = []
    for v in vc:
        name = _HALF_RX.sub("", v.get("layer") or "")
        if not v.get("by_model") or v.get("official") or not v.get("companies") or not re.search(COMPUTE_LAYER, name, re.I):
            continue
        rest = next((w for w in vc if w.get("official") and w.get("basis") == "rest"), None)
        if rest is None:
            rest = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
            vc = vc + [rest]
        why = (f"a group by how they earn, “{name}”, a business the theme's name and its map's layers don't name: in the theme by its own "
               f"industry, in “{_HALF_RX.sub('', rest['layer'])}”")
        for c in v["companies"]:
            rest["companies"] = list(rest.get("companies") or []) + [{**c, "moved": True, "refit": {"from": name, "to": "", "why": why}}]
            rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": name, "to": _HALF_RX.sub("", rest["layer"]), "why": why})
        v["companies"] = []
    return [v for v in vc if v.get("companies") or v.get("official") or not v.get("by_model")], rows


def compute_fit(vc: list[dict], words_of, theme: str) -> tuple[list[dict], list[dict]]:
    """r572 round 2: in a layer whose name says its companies sell computing or infrastructure (COMPUTE_LAYER, a name that says software
    aside), a company a rule or the AI's placement put there (moved there by the split, or placed by the AI; never the map's own pick nor one
    placed by its own words) whose own words don't say it sells computing, capacity, hosting or data centres (says_compute) is placed again:
    in the one layer whose name its own words say, else the layer whose name and definition share most of its words (two or more), else the
    theme's "Other" group; never out of the theme. (the layers, a row for
    each company moved)."""
    tw = kind_stems(theme)
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    rows = []
    for v in own:
        name = _HALF_RX.sub("", v.get("layer") or "")
        if not re.search(COMPUTE_LAYER, name, re.I) or re.search(r"\bsoftware\b", name, re.I):
            continue
        keep, gone = [], []
        for c in v.get("companies") or []:
            text = own_text((words_of(c.get("ticker")) if words_of else None) or c.get("what") or "")
            # (r68e: a property owner whose words name a property type the layer's name names is of it: a tower owner in "Towers, data
            # centres and niche property")
            if not (c.get("moved") or c.get("placed") == "ai") or not text.strip() or says_compute(text) or property_fit(name, text) is True:
                keep.append(c)
                continue
            gone.append((c, text))
        if not gone:
            continue
        v["companies"] = keep
        others = [w for w in own if _HALF_RX.sub("", w.get("layer") or "") != name and len(w.get("companies") or []) >= 2
                  and not re.search(COMPUTE_LAYER, _HALF_RX.sub("", w.get("layer") or ""), re.I)]
        for c, text in gone:
            plain = re.sub(CLOUD_ADJECTIVE, " ", text, flags=re.I)
            # r68e (the live R65 REITs deck: Camden, multifamily apartments, and SBA, towers, sent to "Healthcare property owners" on the
            # words they share with it): never a layer whose name names only property types its words don't
            others_ = [w for w in others if property_fit(_HALF_RX.sub("", w.get("layer") or ""), plain) is not False]
            # e82 (LIVE18A-004, the live R80 REITs: Pillarstone Capital REIT, "engaged in investing in, owning and operating commercial
            # properties", put in "Mortgage REITs" on the words it shares with it): a layer of lenders only for one whose words say it lends
            if not LENDS_SAYS.search(plain):
                others_ = [w for w in others_ if not LENDING_LAYER.search(_HALF_RX.sub("", w.get("layer") or ""))]
            said = [w for w in others_ if layer_says(w, plain, tw)[1]]
            to, how = (said[0], "its own words say what “{}” is") if len(said) == 1 else (None, "")
            if to is None:
                mine = kind_stems(plain) - tw
                best = max(others_, key=lambda w: len(mine & (kind_stems(f"{w.get('layer')} {w.get('description') or ''}") - tw)), default=None)
                if best is not None and len(mine & (kind_stems(f"{best.get('layer')} {best.get('description') or ''}") - tw)) >= 2:
                    to, how = best, "its own words share most with what “{}” is"
            if to is None:
                to = next((w for w in vc if w.get("official") and w.get("basis") == "rest"), None)
                if to is None:
                    to = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                    vc = vc + [to]
                how = "no other layer's name is said by its own words"
            shown = _HALF_RX.sub("", to["layer"])
            why = (f"its own words don't say it sells computing, capacity, hosting or data centres, what “{name}” is (“cloud” said of another "
                   f"product is a word about that product); " + how.format(shown))
            to["companies"] = list(to.get("companies") or []) + [{**c, "moved": True, "refit": {"from": name, "to": shown, "why": why}}]
            rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": name, "to": shown, "why": why})
    return [v for v in vc if v.get("companies") or v.get("official") or not (v.get("by_model") or v.get("scale"))], rows


_SAID_HOW = {"distr", "retai", "manuf", "maker", "suppl", "trade", "tradi", "store", "shop"}


def words_support(name: str, text: str, theme: str, description: str = "") -> bool:
    """r58: whether a company's own words say a word of a layer's name, a word of how a business earns included ("distribution" said by
    "distributing"), the theme's own words and plain words aside: a layer an earlier published version had keeps a member whose words say it."""
    pf = property_fit(name, text)          # r68e: a property owner's layer by the kind of property its words name
    if pf is not None:
        return pf
    low = re.sub(r"\s*\((?:larger|smaller)\)$", "", str(name or "")).lower()
    ns = {_stem(w) for w in re.findall(r"[a-z0-9]+", low) if len(w) >= 4 and w not in _KIND_PLAIN} - kind_stems(theme) - _stems("other companies and")
    ns -= _HOW_STEMS - _SAID_HOW            # a word any company says ("business", "services") says no layer
    mine = {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) >= 4}
    # r60: words that say the layer's concept say it too (concept_said: "direct-to-home" of "satellite distribution")
    return (bool(ns) and bool(ns & mine)) or bool(concept_said(name, text, description))


def structure_quote(q: str) -> bool:
    """e79: whether a quoted sentence only tells how a company is held, financed or taxed (sec.structure_only: a REIT's tax election, its
    operating partnership), never what it owns or does."""
    from .sec import reit_tax_said, structure_only
    q = str(q or "")
    return bool(q.strip()) and (structure_only(q) or reit_tax_said(q)) and \
        not re.search(r"\b(?:owns?|operat(?:es?|ing)(?! partnership)|leases?|develop(?:s|ing)?|acquir(?:es?|ing)|invest(?:s|ing)? in)\b", q, re.I)


def prints_layer(v: dict, text: str, name: str) -> bool:
    """r582: whether a company's own words hold a sentence a deck can print as its line that says a word of a layer's name (layer_line):
    a company joins a layer by a rule only on words its line can show (the name the deck shows, never only the map's earlier one)."""
    return bool(layer_line("", text, name, _HALF_RX.sub("", v.get("layer") or ""), v.get("description") or ""))


def said_count(v: dict, text: str, theme_words: set) -> int:
    """r582: how many of the words of a layer's names (kind_stems, the theme's own aside) a company's own words say (name_says' reading)."""
    mine = kind_stems(str(text or "").lower())
    near = lambda a, b: a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))      # noqa: E731
    names = kind_stems(" ".join(str(x) for x in (v.get("was"), _HALF_RX.sub("", v.get("layer") or "")) if x).lower().replace("-", " ")) - theme_words
    # r60: a concept of the layer its words say counts as a word of its name said (concepts_said)
    return sum(1 for b in names if any(near(a, b) for a in mine)) + concepts_said(_HALF_RX.sub("", v.get("layer") or ""), text, v.get("description") or "")


def words_from_other(vc: list[dict], words_of, theme: str) -> tuple[list[dict], list[dict]]:
    """r582 (R58.2, the live R58.1 Biotech deck: 471 of 820 companies in "Other", 389 of them with words of their own stored, nearly all put
    there by the words placement before their descriptions were stored, a kept "no layer" never placed again): after every rule, a company
    the words placement left in the theme's "Other" group (placed by words, in no layer, moved there by no rule with a reason) whose own
    words, as stored now, say a layer's name goes to the layer of two or more whose name they say the most of, when one does more than any
    other and its line can show it (prints_layer); the reason printed. (the layers, a row for each company moved)."""
    tw = kind_stems(theme)
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    if rest_v is None or not rest_v.get("companies"):
        return vc, []
    homes = [v for v in vc if not v.get("official") and not v.get("scale") and len(v.get("companies") or []) >= 2 and layer_says(v, "", tw)[0]]
    rows, left = [], []
    for c in rest_v["companies"]:
        if c.get("placed") != "words" or c.get("fit") or isinstance(c.get("refit"), dict) or isinstance(c.get("unfit"), dict) \
                or c.get("fallback") or c.get("held") or c.get("unread"):
            left.append(c)
            continue
        text = without_name(own_text((words_of(c.get("ticker")) if words_of else None) or ""), c.get("name") or "")
        said = [v for v in homes if text.strip() and not no_words(text) and layer_says(v, text, tw)[1]]
        if said:
            n_ = {id(v): said_count(v, text, tw) for v in said}
            said = [v for v in said if n_[id(v)] == max(n_.values())]
        if len(said) != 1 or not prints_layer(said[0], text, c.get("name") or ""):
            left.append(c)
            continue
        to = _HALF_RX.sub("", said[0]["layer"])
        why = f"its own words say what “{to}” is (placed in no layer before its own words were stored)"
        said[0]["companies"] = list(said[0]["companies"]) + [{**c, "moved": True, "placed_by": "by_words",
                                                               "refit": {"from": "", "to": to, "why": why}}]
        rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": "", "to": to, "why": why})
    rest_v["companies"] = left
    return vc, rows


def printed_names(vc: list[dict], words_of) -> tuple[list[dict], list[dict]]:
    """r582 (R58.2, the live R58.1 Media US deck: "Connected-TV platforms and radio broadcasting" over Roku, "the leading TV streaming
    platform", and iHeartMedia, "the only major multi-platform audio media company", neither line saying connected, radio or broadcasting):
    after every rule, a named layer none of whose companies' own words hold a line that says a word of its name (prints_layer) takes the
    name it had (the map's own, or one in "aka") that the most of its companies' lines say, when one does; the name it was given stays in
    "aka". (the layers, a row for each layer renamed)."""
    rows = []
    for v in vc:
        if v.get("official") or not v.get("companies") or v.get("scale"):
            continue
        shown = _HALF_RX.sub("", v.get("layer") or "")
        texts = [(own_text((words_of(c.get("ticker")) if words_of else None) or ""), c.get("name") or "") for c in v["companies"]]
        texts = [(t, n) for t, n in texts if t.strip() and not no_words(t)]
        if not texts or not layer_words(shown) or any(layer_line("", t, n, shown) for t, n in texts):
            continue
        had = [x for x in dict.fromkeys([v.get("was") or ""] + list(v.get("aka") or [])) if x and _HALF_RX.sub("", x) != shown and layer_words(x)]
        n_ = {x: sum(1 for t, n in texts if layer_line("", t, n, x)) for x in had}
        best = max(n_.values(), default=0)
        if not best:
            continue
        new = next(x for x in had if n_[x] == best)
        v["layer"] = new + v["layer"][len(shown):]
        v["aka"] = list(dict.fromkeys((v.get("aka") or []) + [shown]))
        v.pop("description", None)
        rows.append({"layer": shown, "renamed": new, "why": f"none of its companies' own words say a word of “{shown}”; {best} of their "
                                                            f"lines say “{new}”, a name it had: that name stays"})
    return vc, rows


def single_layers(vc: list[dict], words_of, theme: str, earlier: dict | None = None) -> tuple[list[dict], list[dict]]:
    # r60: a layer the map named whose one company's own words say what it is, in a line a deck prints, is kept with it (single_kept)
    """r572 (R57.2, the release gate on the live R57.1 decks: 16 layers of one company, "Cold chain operators" holding one company whose own
    words say no word of it, "Data centres, hosting and networks" in an oil theme); r582 (R58.2, the live R58.1 decks: 19 layers of one
    company): a layer holding one company whose own words say its name gains the companies whose own words say it too, from "Other" or from
    a layer of three or more whose name their words don't say. A layer that gains none is not kept with one company (r58 kept a published one;
    `earlier` is no longer read): its company goes to the layer of two or more whose name its own words say the most of, when one does more
    than any other, else to the theme's "Other" group, with the reason printed. (the layers, a row for each company moved)."""
    tw = kind_stems(theme)
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    rows = []
    text_of = lambda c: own_text((words_of(c.get("ticker")) if words_of else None) or c.get("what") or "")      # noqa: E731
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    for v in own:
        cos = v.get("companies") or []
        if len(cos) != 1:
            continue
        c = cos[0]
        text = text_of(c)
        named = not (v.get("by_model") or v.get("by_place") or v.get("industry_group"))
        # r582 (R58.2, the live R58.1 decks: 19 layers of one company, "Specialty alloys and forged components" holding Mishra Dhatu Nigam
        # while Bharat Forge, "forged and machined components", sat in "Other"): a layer of one company first gains the companies whose own
        # words say its name, from "Other" or from a layer of three or more whose name their words don't say (never a company whose words
        # were checked for its layer or that the contract holds there); a layer that gains one is a layer of two or more
        if text.strip() and layer_says(v, text, tw)[1]:
            gained = []
            for w in vc:
                if w is v or (w.get("official") and w.get("basis") != "rest") or w.get("scale"):
                    continue
                rest_ = bool(w.get("official"))
                if not rest_ and (w.get("industry_group") or len(w.get("companies") or []) < 3):
                    continue
                for x in list(w.get("companies") or []):
                    t_ = text_of(x)
                    if not t_.strip() or x.get("verified") or x.get("held") or x.get("held_published") or x.get("kept_member") \
                            or not layer_says(v, t_, tw)[1] or (not rest_ and layer_says(w, t_, tw)[1]) or not prints_layer(v, t_, x.get("name") or ""):
                        continue
                    if not rest_ and len(w["companies"]) - 1 < 2:
                        break
                    why = (f"its own words say what “{shown(v)}” is" + ("" if rest_ else f", not what “{shown(w)}” is")
                           + f", so it joins the layer's one company, {c.get('name') or c.get('ticker')}")
                    w["companies"] = [y for y in w["companies"] if y is not x]
                    gained.append({**{k: y for k, y in x.items() if k not in ("sold_by", "placed_by", "fit")}, "moved": True,
                                   "refit": {"from": "" if rest_ else shown(w), "to": shown(v), "why": why}})
                    rows.append({"ticker": x.get("ticker"), "name": x.get("name"), "from": "" if rest_ else shown(w), "to": shown(v), "why": why})
            if gained:
                v["companies"] = list(cos) + gained
                continue
            # r60 (R60, the owner's outside review of the live R59 decks, P0 "protect evidence-backed singleton categories": General
            # Insurance Corporation of India, "engaged in the business of Reinsurance", moved out of its own "Reinsurance" into "Other" only
            # because it was the layer's one company; Dish TV out of "Cable and satellite distribution"): a layer the map named whose one
            # company's own words say what it is, in a line a deck prints (prints_layer, the layer's concept read too), stays with that
            # company: a valid role is never hidden because one company plays it. It is said to be one company (single_kept), and no
            # median, range or ranking is worked out for it (a statistic needs MIN_BASE companies). One whose words don't say it folds
            line = layer_line("", text, c.get("name") or "", shown(v), v.get("description") or "") if named and not no_words(text) else ""
            if line:
                v["single_kept"] = f"one company, its own words: “{line}”; no median, range or ranking for one company"
                continue
        # r582 (R58.2): no layer stays with one company (r58 kept a published one whose member's words say its name: the live R58.1 decks
        # printed 19 of them): its company goes to the layer whose name its own words say the most of, when one does more than any other
        homes = [w for w in own if w is not v and len(w.get("companies") or []) >= 2 and text.strip() and layer_says(w, text, tw)[1]
                 and prints_layer(w, text, c.get("name") or "")]
        if len(homes) > 1:
            said_n = {id(w): said_count(w, text, tw) for w in homes}
            top_n = max(said_n.values())
            homes = [w for w in homes if said_n[id(w)] == top_n]
        to = homes[0] if len(homes) == 1 else None
        if to is None:
            to = next((w for w in vc if w.get("official") and w.get("basis") == "rest"), None)
            if to is None:
                to = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                vc = vc + [to]
        why = (f"a layer of one company, “{_HALF_RX.sub('', v['layer'])}”, " + ("made by how its companies earn" if not named else
               "whose name its own words don't say" if not (text.strip() and layer_says(v, text, tw)[1]) else
               "whose name no other company's own words say") + (f"; its own words say what “{_HALF_RX.sub('', to['layer'])}” is"
                                                                 if not to.get("official") else "; no other layer's name is said by its own words"))
        to["companies"] = list(to.get("companies") or []) + [{**c, "moved": True, "refit": {"from": _HALF_RX.sub("", v["layer"]),
                                                                                             "to": _HALF_RX.sub("", to["layer"]), "why": why}}]
        v["companies"] = []
        rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": _HALF_RX.sub("", v["layer"]), "to": _HALF_RX.sub("", to["layer"]),
                     "why": why})
    if not rows:
        return vc, []
    return [v for v in vc if v.get("companies") or v.get("official")], rows


def theme_clause(text: str, name: str, theme_words: set) -> str:
    """r581: the clause of a company's own words that says a word of the theme's work (its own name's words aside: "Howmet Aerospace Inc. is
    a Delaware corporation" says nothing of aerospace), as a deck quotes it; "" when none does."""
    from .theme_changes import QUOTE_MAX
    named = {w.lower() for w in re.findall(r"[A-Za-z]+", str(name or ""))}
    for sent in re.split(r"(?<=[a-z0-9)”\"])\.\s+(?=[A-Z])", str(text or "")):
        sent = re.sub(r"\s*\([^()]*\)", "", sent)
        upto = ""
        for clause in re.split(r"(?<=[,;])\s+", sent):
            upto = f"{upto} {clause}".strip()
            said = " ".join(w for w in re.findall(r"[A-Za-z][A-Za-z&-]*", clause) if w.lower() not in named)
            if kind_stems(said) & theme_words:
                # the sentence up to that clause, else the clause alone
                one = next((x.strip(" .,;:") for x in (upto, clause) if len(x.strip(" .,;:")) <= QUOTE_MAX), "")
                if one:
                    return one.replace("“", "‘").replace("”", "’")
    return ""


def layer_answer_removals(vc: list[dict], placements: dict, words_of, theme: str, facts_for=None) -> tuple[list[dict], dict]:
    """r572 (R57.2, the release gate's "layer-only removal" on the live R57.1 inputs: Abbott and Johnson & Johnson out of Medical devices,
    Spotify and Sirius XM out of Media, JPMorgan out of Payments, each on the map check's "no" for one or two of its groups): a company the
    check left out on one layer's answer alone ("no", "unbacked"), and so out of the theme, is decided by its own stored words. Words that
    say the theme's own business (a word of the theme's name or of a layer's name) keep it in the theme, in its "Other" group: a mismatch
    with one layer is a reason to place it elsewhere, never to remove it (its answer is listed as a layer decision, "layer_no"). Words that
    say none of it leave it out as another business, their first sentence said ("scope"). With no words of its own, its official industry
    decides the same way (r572 round 2); with neither, it stays: an empty answer moves nothing.
    (the layers, the placements)."""
    from .theme_changes import first_sentence
    inside = {c.get("ticker") for v in vc for c in v.get("companies") or []}
    tw = kind_stems(" ".join([str(theme)] + [n for v in vc if not v.get("official") for n in _names(v)]))
    keep, back, moved = [], [], []
    for x in placements.get("dropped") or []:
        s_ = x.get("ticker") if isinstance(x, dict) else None
        if not s_ or s_ in inside or x.get("said") not in ("no", "unbacked"):
            keep.append(x)
            continue
        try:
            w = (words_of(s_) if words_of else "") or ""
        except Exception:
            w = ""
        quote = first_sentence(w)
        try:
            ind = str(((facts_for(s_) if facts_for else None) or {}).get("industry") or "").split(">")[-1].strip()
        except Exception:
            ind = ""
        # round 2: with no words of its own, its official industry decides; with neither, the answer alone moves nothing: it stays
        says_theme = bool(kind_stems(own_text(w)) & tw) if quote else (not ind or bool(kind_stems(ind) & tw))
        if not quote and ind and not says_theme:
            keep.append({**x, "said": "scope", "scope": f"another business: filed under {ind}, and no description of its own is stored"})
            continue
        if says_theme:
            groups = " or ".join(f"“{g}”" for g in (x.get("groups") or [])[:2]) or "its group"
            # r581 (the owner's open items on the live R57.2 Aerospace deck: BWX, Curtiss-Wright, Howmet and Palantir added "with no
            # stated reason"): the sentence of its own words that says the theme's work, quoted
            # (a word of the theme's own name first, then one of its layers' names: what kept it)
            said_s = (theme_clause(own_text(w), x.get("name") or "", kind_stems(theme)) or theme_clause(own_text(w), x.get("name") or "", tw)) if quote else ""
            said_ = ((f"its own words say the theme's work: “{said_s}”" if said_s else "its own words say the theme's work") if quote else f"its official industry ({ind}) is of the theme's work" if ind else
                     "no description of its own or official industry is stored, so the answer alone moves nothing")
            # (one with neither words nor an official industry stored is not checked yet: never said to be kept on an industry)
            back.append({"ticker": s_, "name": x.get("name") or s_, "what": "", "verified": False, "base": bool(quote or ind), "basis": "words",
                         "industry": ind, "cap": None, "placed": "words",
                         # r58 (the live R57.2 decks printed "filed under an official industry of the theme; True" for these): why, in words
                         "kept_member": f"kept in the theme: the map's check said no for {groups} only, one layer's answer; {said_}",
                         "theme": {"why": f"the map's check said no for {groups} only, one layer's answer; {said_}"}})
            moved.append(x)
            continue
        keep.append({**x, "said": "scope", "scope": f"another business: its own words say “{quote}”"})
    if not back and keep == list(placements.get("dropped") or []):
        return vc, placements
    if back:
        rest = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
        if rest is None:
            rest = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
            vc = vc + [rest]
        rest["companies"] = list(rest.get("companies") or []) + back
    placements = {**placements, "dropped": keep}
    if moved:
        placements["layer_no"] = list(placements.get("layer_no") or []) + moved
    for k_ in ("placed", "total"):          # (round 2: the members it keeps are counted, "Considered 81 · membership checked 86 of 81")
        if back and isinstance(placements.get(k_), int):
            placements[k_] += len(back)
    if not keep:
        placements = {k: v for k, v in placements.items() if k != "dropped"}
    return vc, placements


def whole_company_out(vc: list[dict], words_of, theme: str) -> tuple[list[dict], list[dict]]:
    """p57 (R56 audit MD-2: "3M Co (whole company)" in Medical devices after its health business was spun off): a company whose own words
    call it a conglomerate or diversified group, and whose words share no word with the theme's own business (the theme's name, any
    layer's name or definition), leaves the theme with that printed reason ("another business", its official industry said): its filing
    alone keeps no company in. (the layers, the companies out: [{ticker, name, industry, why}])."""
    tw = kind_stems(theme)
    vocab = {w for w in _name_words(str(theme).lower())}
    for v in vc:
        if not v.get("official"):           # r571: the layers' names, and their definitions' words taken whole ("protected" is no "protective")
            vocab |= {w for n in _names(v) for w in _name_words(n.lower())}
            vocab |= {w for w in _name_words(_CONTRAST.sub(" ", _CUSTOMERS.sub(" ", str(v.get("description") or ""))).lower()) if len(w) >= 6}
    vocab -= _TARGET_FILLER
    out, gone = [], set()
    for v in vc:
        for c in v.get("companies") or []:
            text = own_text((words_of(c.get("ticker")) if words_of else None) or c.get("what") or "")
            if len(text.strip()) < 40 or not _CONGLOMERATE.search(text) or not _FIELDS.search(text):
                continue                     # r571: its words must name the businesses it is in (Alphabet's say only that it holds Google)
            mine = _name_words(text.lower())
            # r571 (the live R57 Medical devices deck: 3M kept on "electrical" against "electromedical", "protective" against "protected"):
            # the very word of a layer's name says the theme's business; a word's start ("electr" of "electrotherapy") says nothing
            if (mine & (vocab - _WHOLE_PLAIN)) or kind_stems(text) & tw:
                continue
            gone.add(id(c))
            out.append({"ticker": c.get("ticker"), "name": c.get("name") or c.get("ticker"), "industry": c.get("industry") or "",
                        "why": "another business: its own words describe a group of other businesses, none of them the theme's (the placement contract)"})
    if not gone:
        return vc, []
    vc = [{**v, "companies": [c for c in v.get("companies") or [] if id(c) not in gone]} for v in vc]
    return [v for v in vc if v.get("companies") or not (v.get("by_model") or v.get("by_place") or v.get("industry_group") or v.get("official"))], out


# p57: the kinds of business a way of earning's label names, each with the words that say it: a layer made by how its companies earn is
# named by the kinds its members' own words say, never by a kind none of them is (two education apps under "Hotels, travel and consumer
# services"). Only a label that names several kinds has them.
MODEL_KINDS = {
    "consumer_services": (("Hotels and resorts", r"\bhotels?\b|\bresorts?\b|hospitality"),
                          ("Travel services", r"\btours?\b|\btravel\b|holidays?"),
                          ("Restaurants and food service", r"restaurants?|quick[- ]service|food service|dining|\bcaf[eé]s?\b"),
                          ("Education and courses", r"educat\w*|\bschools?\b|coaching|\bcourses?\b|tuition|\blearning\b"),
                          ("Leisure and entertainment", r"amusement|theme parks?|cinemas?|multiplex|entertainment cent\w*"),
                          ("Wellness and fitness", r"wellness|salons?|fitness|\bgyms?\b")),
    "resources": (("Mining", r"\bmin(?:e|es|ing|ers?)\b|\bores?\b|\bcoal\b|bauxite|quarr\w*"),
                  ("Oil and gas", r"\boil and gas\b|petroleum|crude|drilling|\bnatural gas\b|exploration and production"),
                  ("Farming and plantations", r"plantations?|\btea\b|\bcoffee estates?\b|\bestates?\b|\bfarm\w*|\bcrops?\b|\bagri\w*|"
                                              r"sugarcane|rubber plantations?")),
    # r60 (LIVE9A-006, the live R59 US Oil and gas page: royalty trusts in a layer named "Designs licensed for royalties"): royalties on
    # designs and patents apart from royalties on oil, gas and mineral production
    "royalties": (("Designs licensed for royalties", r"\bpatents?\b|\bdesigns?\b|\bintellectual property\b|\blicens(?:e|es|ing|ed)\b(?! agreement)"),
                  ("Oil, gas and mineral royalty owners", r"\broyalty (?:interests?|trusts?)\b|\bmineral (?:and royalty )?interests?\b|"
                                                          r"\boil and (?:natural )?gas (?:properties|production)\b|\bnet profits? interests?\b|"
                                                          r"\boverriding royalt\w*")),
}


def kinds_name(model: str, texts: list[str]) -> str:
    """p57: a layer's name from the kinds of its way of earning (MODEL_KINDS) its members' own words say, the most said first (two at most,
    "Hotels and resorts and travel services"); "" when the label names no kinds or none is said."""
    kinds = MODEL_KINDS.get(model or "") or ()
    n = [(sum(1 for t in texts if re.search(rx, t or "", re.I)), i, nm) for i, (nm, rx) in enumerate(kinds)]
    said = [nm for k, i, nm in sorted(n, key=lambda x: (-x[0], x[1])) if k]
    if not said:
        return ""
    return said[0] if len(said) == 1 else f"{said[0]} and {said[1][:1].lower()}{said[1][1:]}"


# r572 round 2: the words of a layer's name that say a business (the release gate's test: no joining word, no word any company is or does)
NAME_GENERIC = {"and", "or", "of", "the", "for", "in", "to", "with", "by", "on", "from", "other", "others", "own", "their", "they", "them",
                "company", "companies", "firms", "players", "business", "businesses", "group", "groups", "service", "services", "product",
                "products", "goods", "consumer", "consumers", "customer", "customers", "client", "clients", "makers", "maker", "producers",
                "producer", "suppliers", "supplier", "providers", "provider", "sellers", "seller", "owners", "owner", "operators",
                "partners", "specialty", "speciality", "diversified", "integrated", "sized", "small", "smaller", "large", "larger", "mid",
                "scale", "wide", "broad", "general", "focused", "led", "based", "commercial", "listed", "segment", "segments", "related",
                "allied", "plus", "global", "domestic", "new", "solutions", "systems"}
_NAME_SUFFIXES = ("ations", "ation", "ings", "ing", "ers", "er", "ies", "es", "s", "ed", "al")


def _name_stem(w: str) -> str:
    for suf in _NAME_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)][:5]
    return w[:5]


def says_name(name: str, texts) -> bool | None:
    """r572 round 2: whether any of the texts says a word of a layer's name that says a business; None when the name has none."""
    nw = {_name_stem(w) for w in re.findall(r"[a-z0-9]+", str(name or "").lower().replace("&", " and ")) if len(w) > 2 and not w.isdigit()
          and w not in NAME_GENERIC}
    if not nw:
        return None
    for t in texts:
        tw = {_name_stem(w) for w in re.findall(r"[a-z0-9]+", str(t or "").lower().replace("&", " and ")) if len(w) > 2}
        if any(a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))) for a in nw for b in tw):
            return True
    return False


def in_place_name(name: str, word: str, texts: list[str]) -> str:
    """r58: a layer's name with the words none of its companies say (NAME_GENERIC aside) taken out and the first of them replaced by `word`,
    their own word, plural where it was ("Commercial airframe integration" over aircraft makers: "Commercial aircraft"; "Commercial and business
    lenders" over banks: "Commercial and business banks"); "" when no word of the name is unsaid or `word` is in it already."""
    if not word or word.lower() in name.lower():
        return ""
    unsaid = [w for w in re.findall(r"[A-Za-z]{4,}", name) if w.lower() not in NAME_GENERIC and says_name(w, texts) is False]
    if not unsaid:
        return ""
    # r581 (the R58 replay of Regional banks: "Real estate-focused lenders" over banks, none of whose words it says, became "Bank-focused"):
    # a name with no word left whole (a compound, "estate-focused", goes with its unsaid part) keeps no meaning of the map's; the word in
    # brackets instead (the caller's fallback)
    gone = {w.lower() for w in unsaid}
    if not any(not ({p.lower() for p in t.split("-")} & gone) for t in re.findall(r"[A-Za-z][A-Za-z-]{3,}", name)):
        return ""
    first = unsaid[0]
    put = word + ("s" if first.lower().endswith("s") and not word.lower().endswith("s") else "")
    # r63e (LIVE10A-034: "Regional integrated producers" became "Cements integrated producers"): a word put in place of one that is not
    # plural, a word before its noun, is singular ("Cement integrated producers")
    if not first.lower().endswith("s") and re.search(r"[^s]s$", put, re.I) and len(put) > 4:
        put = put[:-1]
    out = re.sub(r"\b" + re.escape(first) + r"\b", put, name, count=1)
    for w in unsaid[1:]:
        out = re.sub(r"\s*\b" + re.escape(w) + r"\b", "", out, count=1)
    out = re.sub(r"\s+(?:and|of|for)\s*$", "", re.sub(r"\s{2,}", " ", out)).strip()
    return out[:1].upper() + out[1:]


def property_rename(companies: list[dict], was: str, name: str, text) -> str:
    """r68e: why a property owner's layer keeps the name it had (`was`) against a new one (`name`): both names name property types
    (layer_property_types), fewer than half of its companies whose own words name a property type name one of the new name's, and more than
    half name one of the old's; "" else. `text(c)`: a company's own words."""
    if not layer_property_types(was) or not layer_property_types(name) or layer_property_types(was) == layer_property_types(name):
        return ""
    typed = [c for c in companies if company_property_types(text(c))]
    if len(typed) < 2:
        return ""
    new_n = sum(1 for c in typed if property_fit(name, text(c)))
    old_n = sum(1 for c in typed if property_fit(was, text(c)))
    if new_n * 2 >= len(typed) or old_n * 2 <= len(typed):
        return ""
    from collections import Counter
    kinds = Counter(t for c in typed for t in company_property_types(text(c)) if t in layer_property_types(was)).most_common(2)
    return (f"its companies' own words name property of “{was}” ({old_n} of the {len(typed)} that name a kind of property: "
            f"{' and '.join(k for k, _ in kinds)}), {new_n} of them what “{name}” names: the name it had stays")


# e81 (LIVE17A-004, after e80: the live US REITs "Towers, data centres and niche property" holding InPoint Commercial Real Estate Income, a
# lender, and the non-traded Blackstone Real Estate Income Trust, Hines Global Income Trust and Ares Real Estate Income Trust; KLX Energy
# Services, a $21 m oilfield services company filed under "Oil & Gas Field Services", kept in "Integrated oil majors" by its published layer;
# Fertilizers and agrochemicals' "Property developers" layer of companies none of whose own words says property is their business): a kind of
# company a layer can never hold, whatever placed or held it there. Each is a fact of the company's own records: its words (a lender's), its
# name and words (a non-traded vehicle's), its official industry and market value (an oilfield services company's), its principal sentence
# (a property business's)
LENDS_SAYS = re.compile(r"\boriginat(?:e|es|ed|ing|ion)\b[^.;]{0,80}?\b(?:loans?|debt|mortgages?|credit)\b|\bfirst[- ]mortgage\s+loans?\b|"
                        r"\bmezzanine\s+loans?\b|\b(?:commercial\s+)?real\s+estate\s+(?:debt|credit|loans?|lending)\b|\bCRE\s+(?:debt|loans?|credit)\b|"
                        r"\breal\s+estate\s+finance\s+company\b|\bsenior\s+(?:secured\s+)?(?:mortgage\s+)?loans?\b|\bmortgage[- ]backed\s+securities\b|"
                        r"\bagency\s+RMBS\b", re.I)
LENDING_LAYER = re.compile(r"\bmortgage|\bloans?\b|\blend|\bcredit\b|\bfinanc", re.I)
OWNER_LAYER = re.compile(r"\blandlords?\b|\bowners?\b|\bpropert(?:y|ies)\b|\btowers?\b|data cent(?:er|re)s?|\breal estate\b", re.I)
SPECIALIST_LAYER = re.compile(r"\btowers?\b|data cent(?:er|re)s?", re.I)
NON_TRADED_NAME = re.compile(r"\bIncome\s+(?:Trust|REIT|Fund)\b|\bReal\s+Estate\s+Income\b|\bNAV\s+REIT\b", re.I)
NON_TRADED_SAYS = re.compile(r"\bnon-?(?:traded|listed|exchange[- ]traded)\b|\bperpetual[- ]life\b|\bnet\s+asset\s+value\s+per\s+share\b|"
                             r"\bnot\s+listed\s+on\s+(?:a|any)\s+(?:national\s+)?securities\s+exchange\b", re.I)
MAJORS_LAYER = re.compile(r"\b(?:super)?majors?\b", re.I)
SERVICES_INDUSTRY = re.compile(r"\bfield\s+services?\b|\bequipment\b|\bdrilling\b|\bservices?\b", re.I)
MAJOR_MIN = 1000.0              # a market value under this (in $ million or ₹ crore) is never an integrated major's
PROPERTY_LAYER = re.compile(r"\bpropert(?:y|ies)\b|\breal\s+estate\b|\brealty\b", re.I)
PROPERTY_THEME = re.compile(r"\bpropert|\breal\s*estate|\brealty|\breit|\bhous|\bhomes?\b|\bconstruct|\binfra|\blandlord|\bbuilding", re.I)
PROPERTY_SAYS = re.compile(r"\breal\s+estate\b|\brealty\b|\bpropert(?:y|ies)\b|\bresidential\s+(?:projects?|development)|"
                           r"\b(?:housing|township|commercial)\s+(?:projects?|development)", re.I)
# e82 (LIVE18A-004, the live R80 REITs: Omega Healthcare, a healthcare property owner whose words also name "real estate loans", and
# Blackstone Real Estate Income Trust, one segment of nine "Investments in Real Estate Debt", moved to "Mortgage REITs" on one phrase):
# words that say a company owns, leases or invests in property it holds (never "owned by" a borrower or a sponsor). A lender is one whose
# principal words (its business sentence and the next) say it lends and none of these
OWNS_SAYS = re.compile(r"\b(?:own|owns|owning|owned)\b(?!\s+(?:and\s+operated\s+)?by\b)[^.;]{0,80}?\b(?:propert(?:y|ies)|facilities|buildings|"
                       r"communities|portfolio|real\s+estate|farmland|hotels?|apartments?|cent(?:er|re)s)\b|\btriple[- ]net\b|"
                       r"\bnet[- ]leas(?:e|ed|es|ing)\b|\bowning\s+and\s+(?:operating|leasing)\b|"
                       r"\b(?:investing|invests?|investments?)\s+in\b[^.;]{0,40}?\b(?:properties|facilities|buildings)\b", re.I)
# e82 (LIVE18A-004: Medalist Diversified and Presidio Property Trust, owners of retail, office and hotel property, in "Towers, data
# centres and niche property"): a diversified owner of commercial property, by its name or its principal words
DIVERSIFIED_NAME = re.compile(r"\bdiversified\b", re.I)
DIVERSIFIED_SAYS = re.compile(r"\b(?:own|owns|owned|owning)\b[^.;]{0,40}?\bcommercial\s+(?:properties|real\s+estate\s+properties)\b|"
                              r"\bmixed[- ]use\s+properties\b", re.I)


def property_scope_layer(name: str, theme: str) -> bool:
    """e81/e82: a layer of property or real estate in a theme that names no such business: the theme-scope case. e82 (LIVE18A-008, the live
    R80 Regional banks: "Real estate-focused lenders (bank)" emptied into "Other" because its banks' words don't say property is their
    business): a layer of lenders (its name says it lends, LENDING_LAYER) is a layer of a lending business, never of property."""
    name = _HALF_RX.sub("", str(name or ""))
    return bool(PROPERTY_LAYER.search(name)) and not LENDING_LAYER.search(name) and not PROPERTY_THEME.search(str(theme or ""))


def kind_bar(layer: str, c: dict, words, theme: str) -> tuple[str, str]:
    """e81: (why the company is a kind the layer can never hold, the kind of layer it belongs in: "lending" or ""), ("", "") when none."""
    name = _HALF_RX.sub("", str(layer or ""))
    text = own_text(words or c.get("what") or "")
    nm = str(c.get("name") or "")
    if OWNER_LAYER.search(name) and not LENDING_LAYER.search(name):
        # e82: on its principal business (principal_words), never one phrase of a later line: a lender is one whose principal words say it
        # lends and none says it owns property (OWNS_SAYS); its way of earning read as lending counts only when no word of it says so
        lead = principal_words(text) if text.strip() else ""
        m = LENDS_SAYS.search(lead) if not OWNS_SAYS.search(lead) else None
        if m or (c.get("model") == "lending" and c.get("model_confidence") in ("high", "medium") and not OWNS_SAYS.search(text)):
            said = f"its own words say it lends (“{m.group(0)}”)" if m else "its way of earning is interest on loans it makes"
            return f"{said}; “{name}” is a layer of companies that own property", "lending"
    if SPECIALIST_LAYER.search(name):
        m = NON_TRADED_SAYS.search(text)
        if m or NON_TRADED_NAME.search(nm):
            said = f"its own words say it is a non-traded REIT (“{m.group(0)}”)" if m else "it is a non-traded REIT (its name: an income trust)"
            return f"{said}, a diversified owner, never a layer of towers and data centres", ""
        if property_fit(name, text) is not True and not says_compute(text):
            d = DIVERSIFIED_NAME.search(nm) or DIVERSIFIED_SAYS.search(text)
            if d:
                return (f"a diversified owner of commercial property (its {'name' if DIVERSIFIED_NAME.search(nm) else 'own words'}: "
                        f"“{d.group(0)}”), and its own words name no tower, data centre or computing it sells"), ""
    if MAJORS_LAYER.search(name) and re.search(r"\boil\b|\bgas\b|\benergy\b|\bpetroleum\b|\bintegrated\b", name, re.I):
        ind = plain_industry(c.get("industry") or "")
        cap = c.get("cap")
        if ind and SERVICES_INDUSTRY.search(ind) and not re.search(r"integrated|petroleum|crude", ind, re.I):
            return f"filed under {ind}, a services company; “{name}” names integrated companies", "services"
        if isinstance(cap, (int, float)) and 0 < cap < MAJOR_MIN:
            return f"its market value ({cap:,.0f} million) is far below any integrated major's; “{name}” names large integrated companies", "services"
    if property_scope_layer(name, theme):
        if not PROPERTY_SAYS.search(principal_words(text) if text.strip() else ""):
            # (e82, LIVE18A-008: a reason quotes the sentence that says its business, never a name alone, a forward-looking statement or an
            # offering's proceeds; none when no sentence says it)
            from .theme_changes import work_sentence
            q = first_line(work_sentence(text)) if text.strip() else ""
            return (f"its own words don't say property is its business"
                    + (f" (they say “{q}”)" if q else "") + f"; a {theme} theme holds “{name}” only for those whose do"), ""
    return "", ""


def first_line(text: str) -> str:
    """e81: a company's words' first sentence, as a reason quotes it (at most 120 characters, on a clause or a whole word)."""
    one = (_sentences(" ".join(str(text or "").split())) or [""])[0].rstrip(" .;")
    if len(one) <= 120:
        return one
    cut = max(one.rfind(", ", 0, 120), one.rfind("; ", 0, 120))
    return (one[:cut] if cut > 40 else one[:one.rfind(" ", 0, 120)]).rstrip(" ,;:") + "…"


def kind_bars(vc: list[dict], words_of, theme: str) -> tuple[list[dict], list[dict]]:
    """e81: the last step of the placement: each company in a layer its own records say it can never be of (kind_bar) goes to the layer of
    its kind when the theme has one (a lender to a layer of lenders; an oilfield services company to a layer of services), else to "Other";
    the reason printed ("refit"). (the layers, the moves)."""
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    rows = []
    for v in [v for v in vc if not v.get("official") and v.get("layer")]:
        keep = []
        for c in v.get("companies") or []:
            why, kind = kind_bar(v["layer"], c, (words_of(c.get("ticker")) if words_of else None), theme)
            if not why:
                keep.append(c)
                continue
            to = None
            if kind == "lending":
                to = next((w for w in vc if w is not v and not w.get("official") and LENDING_LAYER.search(_HALF_RX.sub("", w.get("layer") or ""))), None)
            elif kind == "services":
                homes = [w for w in vc if w is not v and not w.get("official") and re.search(r"\bservices?\b", _HALF_RX.sub("", w.get("layer") or ""), re.I)]
                small = [w for w in homes if str(w.get("layer") or "").endswith("(smaller)")]
                to = (small or homes or [None])[0]
            to = to or rest_v
            if to is None:
                keep.append(c)
                continue
            shown = _HALF_RX.sub("", to.get("layer") or "")
            to["companies"] = list(to.get("companies") or []) + [{**{k: x for k, x in c.items() if k not in ("held_published", "fit", "sold_by")},
                                                                  "moved": True, "refit": {"from": _HALF_RX.sub("", v["layer"]),
                                                                                           "to": "" if to is rest_v else shown, "why": why}}]
            rows.append({"ticker": c.get("ticker"), "name": c.get("name") or c.get("ticker"), "from": _HALF_RX.sub("", v["layer"]),
                         "to": shown, "why": why})
        v["companies"] = keep
    if rows:
        vc = [v for v in vc if v.get("companies") or v.get("official")]
    return vc, rows


def property_moves(vc: list[dict], words_of) -> tuple[list[dict], list[dict]]:
    """r68e (R68, the owner's review of the live R66 REITs deck, P0 "source-backed classes": Camden, multifamily apartments, in a layer of
    manufactured housing; the live map's catch-all "Towers, data centres and niche property" holding office, retail, hotel and apartment
    owners): after every rule, a company in a property owner's layer whose own words name only kinds of property its name doesn't
    (property_fit False) goes to the layer whose name names the kind its words name (the most of them, a lease form such as net lease
    counted only when they name no other; on a tie, the kind its words name first), else to the theme's "Other" group; the reason quotes
    the words. (the layers, a row for each company moved)."""
    named = [v for v in vc if not v.get("official") and v.get("layer") and layer_property_types(v["layer"])]
    if not named:
        return vc, []
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    rows = []
    for v in named:
        name = _HALF_RX.sub("", v["layer"])
        keep = []
        for c in v.get("companies") or []:
            text = own_text((words_of(c.get("ticker")) if words_of else None) or "")
            if property_fit(name, text) is not False:
                keep.append(c)
                continue
            hits = [(at, ty) for at, ty in _property_hits(text)]
            main = [h for h in hits if h[1] != "net lease"] or hits
            mine = {ty for _, ty in main}
            first = {ty: at for at, ty in main}

            def score(w):
                got = layer_property_types(w["layer"]) & mine
                return (len(got), -min((first[t] for t in got), default=10 ** 6), len(w.get("companies") or []))
            homes = [w for w in named if w is not v and layer_property_types(w["layer"]) & mine]
            to = max(homes, key=score) if homes else rest_v
            m = re.search(PROPERTY_TYPES[[t for t, _, _ in PROPERTY_TYPES].index(main[0][1])][2], text, re.I) if main else None
            quote = m.group(0) if m else main[0][1] if main else ""
            kinds = " and ".join(sorted(mine))
            if to is None:
                keep.append(c)
                continue
            shown = _HALF_RX.sub("", to["layer"])
            why = (f"its own words name {kinds} property (“{quote}”), a kind “{name}” doesn't name; "
                   + (f"“{shown}” names it" if to is not rest_v else "no layer's name names it"))
            to["companies"] = list(to.get("companies") or []) + [{**c, "moved": True, "placed_by": "by_words",
                                                                  "refit": {"from": name, "to": "" if to is rest_v else shown, "why": why}}]
            rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": name, "to": shown, "why": why})
        v["companies"] = keep
    return [v for v in vc if v.get("companies") or v.get("official") or not (v.get("by_model") or v.get("scale"))], rows


# r69e (LIVE13A-001 / LIVE13B-009, the live R67 Cement deck: Burnpur Cement, "a formerly operating cement manufacturer that is now completely
# non-operational", moved from "Other" into "Cement integrated producers (smaller)" by its official industry and way of earning, with its
# words quoted as the reason): words saying the company runs no business now
NOT_OPERATING = re.compile(
    r"\b(?:is|are|remains?|has been|became|was declared)\s+(?:now\s+)?(?:completely\s+|entirely\s+|fully\s+|currently\s+)?"
    r"(?:non[- ]?operational|non[- ]?operating|dormant|defunct|inactive)\b"
    r"|\bnot\s+a\s+going\s+concern\b"
    r"|\b(?:has|had)\s+(?:since\s+)?(?:ceased|discontinued|stopped)\s+(?:all\s+)?(?:of\s+)?(?:its\s+)?(?:business\s+|manufacturing\s+|"
    r"commercial\s+)?(?:operations|production|manufacturing|business)\b(?!\s+(?:of|at|in|from)\b)"
    r"|\bno\s+(?:current\s+)?(?:products|operations)\s+or\s+customers\b", re.I)
NOT_OPERATING_SENTENCES = 3          # read in the first sentences of its own words (a later line of a past unit's closure is no such word)
_NO_BUSINESS_LAYER = re.compile(r"\b(?:shell|dormant|inactive|non[- ]?operat\w*|holding|blank[- ]check)\b", re.I)
# what is made of the theme's own product ("Asbestos Cement Products", "AAC blocks", "cement bags"): the theme's word before one of these
# names another product, not the theme's own as what the company makes
MADE_OF = {"product", "products", "pipe", "pipes", "sheet", "sheets", "block", "blocks", "board", "boards", "brick", "bricks", "tile", "tiles",
           "panel", "panels", "pole", "poles", "bag", "bags", "paint", "paints", "additive", "additives", "admixture", "admixtures", "machinery",
           "equipment", "packaging", "sleeper", "sleepers", "roofing", "based", "fibre", "fiber"}


def not_operating(words) -> str:
    """r69e: the sentence of a company's own words (among its first NOT_OPERATING_SENTENCES) that says it runs no business now, "" when none does."""
    for x in _sentences(" ".join(own_text(words).split()))[:NOT_OPERATING_SENTENCES]:
        if NOT_OPERATING.search(x):
            return x.strip()
    return ""


def cut_end(x: str) -> str:
    """r69e (the live R67 US Steel and metals deck p.8: a quote cut on “the…”; R66 kept a cut off "and…" only): the words before an
    ellipsis never end on a joining word, an article or a possessive ("the", "of", "its", "&"), nor on a mark."""
    x = str(x or "").rstrip(" ,;:-–—“\"'(")
    while " " in x and x.rsplit(" ", 1)[1].lower().strip("“\"'(") in _JOINING | {"&", "its", "their", "our", "his", "her", "this", "these"}:
        x = x.rsplit(" ", 1)[0].rstrip(" ,;:-–—“\"'(")
    return x


def business_text(words, name: str = "") -> str:
    """r69e: the sentences of a company's own words that say what it does now (sold_text's reading, no sentence of a former business), its
    name left out as a whole name only (Shree Digvijay Cement's "manufacture of cement" keeps its "cement"; "Burnpur Cement Ltd is ..." says
    no word of cement by its name)."""
    t = sold_text(words, "")
    nm = [w for w in re.findall(r"[A-Za-z0-9&]+", name or "") if w]
    while nm and t:
        t = re.sub(r"\b" + r"[\s.,]+".join(re.escape(w) for w in nm) + r"\b", " ", t, flags=re.I)
        if nm[-1].lower().strip(".") not in ("ltd", "limited", "inc", "corp", "corporation", "co", "plc", "llc", "company"):
            break
        nm = nm[:-1]
    return " ".join(t.split())


def says_theme_product(text: str, theme_words: set) -> bool:
    """r69e: whether a company's words name the theme's own product as what it makes ("manufacture and sale of cement"), not only what another
    product is made of ("Asbestos Cement Products", "AAC (Aerated Autoclave Concrete) blocks")."""
    from .theme_library import WORDS
    toks = re.findall(r"[A-Za-z]+|[^\sA-Za-z]", re.sub(r"\s*\([^()]*\)", " ", str(text or "")))
    for i, t in enumerate(toks):
        lw = t.lower()
        if not (kind_stems(lw) & theme_words or kind_stems(WORDS.get(lw, "")) & theme_words):
            continue
        # the words of its noun phrase after it ("Asbestos Cement Pressure Pipes": "Pressure Pipes"), up to a mark or a joining word
        after = []
        for x in toks[i + 1:i + 4]:
            if not x.isalpha() or x.lower() in _JOINING:
                break
            after.append(x.lower())
        if not any(x in MADE_OF for x in after):
            return True
    return False


_JOINING = {"and", "or", "of", "in", "for", "to", "with", "at", "by", "the", "a", "an", "from", "through", "under", "as", "is", "are", "which",
            "that", "across", "since", "into", "on"}


def _quote(x: str, n: int = 160) -> str:
    x = " ".join(str(x or "").split()).strip(" .,;:")
    if len(x) > n:
        x = cut_end(x[:x.rfind(" ", 0, n)]) + "…"
    return x.replace("“", "‘").replace("”", "’")


def business_moves(vc: list[dict], words_of, theme: str, published: dict | None = None,
                   moved_before: dict | None = None) -> tuple[list[dict], list[dict]]:
    """r69e (LIVE13A-001, the live R67 Cement deck: Burnpur Cement, "a formerly operating cement manufacturer that is now completely
    non-operational", moved from "Other" into "Cement integrated producers (smaller)" by its official industry and way of earning): after
    every rule, a company whose own words say it runs no business now (not_operating, read in their first sentences) is in no layer of a
    business: it goes to the theme's "Other" group, its words quoted (a layer whose name says it holds such companies keeps them). A company
    with no words of its own is not judged. (the layers, a row for each company moved)."""
    named = [v for v in vc if not v.get("official") and v.get("layer") and v.get("companies")]
    if not named:
        return vc, []
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    rows = []
    for v in named:
        name = _HALF_RX.sub("", v.get("layer") or "")
        if _NO_BUSINESS_LAYER.search(name):
            continue
        keep = []
        for c in v["companies"]:
            stop = not_operating((words_of(c.get("ticker")) if words_of else None) or "")
            if not stop:
                keep.append(c)
                continue
            why = f"its own words say it runs no business now (“{_quote(stop)}”), so it is in no layer of a business it runs"
            rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": name, "to": "", "why": why})
            c_ = {**{k: x for k, x in c.items() if k not in ("sold_by", "placed_by", "fit", "unfit", "single")}, "moved": True,
                  "refit": {"from": name, "to": "", "why": why}}
            if rest_v is None:
                rest_v = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                vc = vc + [rest_v]
            rest_v["companies"] = list(rest_v.get("companies") or []) + [c_]
        v["companies"] = keep
    if not rows:
        return vc, []
    return [v for v in vc if v.get("companies") or v.get("official") or not (v.get("by_model") or v.get("scale"))], rows


def truthful_layers(vc: list[dict], published: dict, evidence, theme: str) -> tuple[list[dict], list[dict]]:
    """p57 (contract 3): (the layers, what was done) with each layer a rule made (by how its companies earn, "by_model"; proposed for the
    companies that fit none, "by_place"; of one official industry, "industry_group"; a half by market value aside) checked against its
    members: a name that none of their own words or industries share a word with (shares_vocabulary; at least one has words of its own) is
    a contradicted name: it takes the name of the kinds its members' words say (kinds_name) when its label names kinds, else the layer is
    not made when it is new to the published version (its companies go to their published layer, else "Other", with why). A layer a rule
    made new to the published version with CONTRACT_SINGLE company or fewer is not made either."""
    from collections import Counter

    from .theme_check import MODELS
    labels = {x[1]: k for k, x in MODELS.items()}
    pub = {_HALF_RX.sub("", str(x or "")) for x in (published or {}).values()}
    other = lambda v: bool(v.get("official")) and v.get("basis") == "rest"      # noqa: E731
    rows, undo = [], []
    for v in vc:
        # p57 (R56 audit IT-1, x57: "Healthcare and digital business process services" renamed "Resale of IT hardware and service delivery"
        # over Sagility and Inventurus, healthcare process services): a rename its largest companies' own words don't bear out, where they
        # say the name it had, is not made: the name it had stays
        was = v.get("was") or ""
        if not v.get("official") and was and was != _HALF_RX.sub("", v.get("layer") or "") and v.get("companies"):
            top = [c for c in sorted(v["companies"], key=lambda c: -(c.get("cap") or 0))
                   if len(own_text(evidence(c.get("ticker")) if evidence else "").strip()) >= 40][:RENAME_TOP]
            text = lambda c: own_text(evidence(c.get("ticker")))      # noqa: E731
            # (r68e: two names of the same kinds of property are told apart by their other words, as before)
            bp_ = layer_property_types(was) != layer_property_types(_HALF_RX.sub("", v["layer"]))
            new_n = sum(1 for c in top if shares_vocabulary(_HALF_RX.sub("", v["layer"]), text(c), c.get("industry"), bp_))
            old_n = sum(1 for c in top if shares_vocabulary(was, text(c), c.get("industry"), bp_))
            # r571 (the live R57 Medical devices deck: "Surgical robotics systems" over its makers of no robots): never back to a name
            # whose own words (none other layer's name says) few of its companies say
            dw = distinct_words({"layer": was}, [x for x in vc if x is not v and not x.get("official")], kind_stems(theme))
            worded_all = [c for c in v["companies"] if len(text(c).strip()) >= 40]
            # (r68e: or, of a property owner's layer, the kind of property its name names: "multifamily" says "Residential landlords")
            says_old = sum(1 for c in worded_all if any(_word_near(a, w) for a in _name_words(text(c).lower()) for w in dw)
                           or property_fit(was, text(c)) is True)
            if dw and worded_all and says_old < CONTRADICTED_SHARE * len(worded_all):
                old_n = 0
            # r572 (R57.2, the live R57.1 Software deck: "Cloud infrastructure and platform providers" renamed "Cloud and AI compute
            # providers" over Microsoft, Oracle, Shopify and Twilio, software and platform houses; both names say "cloud", so the test above
            # saw no difference): the words each name says that the other doesn't, counted in its largest companies' own words
            tn_ = _name_words(str(theme).lower())          # (a word of the theme's own name says nothing of which layer)
            nd = _name_words(_HALF_RX.sub("", v["layer"]).lower()) - _name_words(was.lower()) - _TARGET_FILLER - tn_
            od = _name_words(was.lower()) - _name_words(_HALF_RX.sub("", v["layer"]).lower()) - _TARGET_FILLER - tn_
            says_ = lambda c, ws: any(_word_near(a, w) for a in _name_words(text(c).lower()) for w in ws)      # noqa: E731
            new_d, old_d = sum(1 for c in top if says_(c, nd)), sum(1 for c in top if says_(c, od))
            if nd and od and old_d >= 2 and old_d > new_d * 2 and not (dw and worded_all and says_old < CONTRADICTED_SHARE * len(worded_all)):
                old_n, new_n = max(old_n, old_d), new_d
            # r581 (the owner's open items on the live R57.2 Cybersecurity deck: "Identity and access software" renamed "Identity access and
            # broad enterprise software" over Okta, SailPoint and CyberArk, identity houses; the new name keeps every word of the old, so the
            # test above has nothing of the old's own to count): a rename that only adds words, which no more than half of its largest
            # companies' own words say, joins a business its companies are not: the name it had stays, where most of them say it
            widened = bool(nd and not od and len(top) >= 2 and new_d * 2 <= len(top) and old_n * 2 > len(top))
            # r68e (the live R66 REITs deck: "Residential landlords" renamed "Manufactured housing and RV communities" over its apartment
            # owners, Camden and Mid-America among them, for its three manufactured-housing members): of a property owner's layer, the
            # kinds of property its companies' own words name decide; a new name whose property types fewer than half of them name, where
            # most of them name one of the name it had, is not made
            prop = property_rename(v["companies"], was, _HALF_RX.sub("", v["layer"]), text)
            if prop or (top and (old_n > new_n * 2 or widened) and shares_vocabulary(was, text(top[0]), top[0].get("industry"))):
                shown_name = _HALF_RX.sub("", v["layer"])
                half = v["layer"][len(shown_name):]
                rows.append({"layer": shown_name, "renamed": was, "why": prop or (
                    f"its largest companies' own words say what “{was}” names ({old_n} of {len(top)}); {new_d} of them say the "
                    f"words “{shown_name}” adds: the name it had stays") if prop or (widened and old_n <= new_n * 2) else (
                    f"its largest companies' own words say what “{was}” names, not “{shown_name}” ({old_n} of {len(top)} against {new_n}): "
                    f"the name it had stays")})
                v["layer"], v["description"] = was + half, ""
                v["aka"] = list(dict.fromkeys((v.get("aka") or []) + [shown_name]))
        # r572 round 2 (the release gate on the live R57.1 inputs: "Commercial airframe integration" over Boeing and Embraer, makers of
        # aircraft, and "Commercial and business lenders" over twelve banks, names none of their companies' own words, industries or names say):
        # a layer of the map whose name says no word its companies say keeps its name and adds the noun of the official industry most of its
        # largest companies share, where most of their own words say it too ("Commercial airframe integration (aircraft)")
        if not v.get("official") and len(v.get("companies") or []) >= 2 and not (v.get("by_model") or v.get("by_place") or v.get("industry_group")):
            shown_ = _HALF_RX.sub("", v["layer"])
            # r63e (LIVE10A-034, the live R60 Cement deck: "Cements integrated producers (larger)" beside "Regional integrated producers
            # (smaller)", one layer's two halves by market value under two names): a half's name is its whole layer's, so it is read over both
            # halves' companies, and a rename renames both
            twins = [x for x in vc if x is not v and not x.get("official") and _HALF_RX.search(str(x.get("layer") or ""))
                     and _HALF_RX.sub("", str(x.get("layer"))) == shown_] if _HALF_RX.search(v["layer"]) else []
            texts_ = [" ".join(str(x or "") for x in (evidence(c.get("ticker")) if evidence else "", c.get("what"), c.get("industry"), c.get("name")))
                      for c in v["companies"] + [c for x in twins for c in x.get("companies") or []]]
            if says_name(shown_, texts_) is False:
                big = [c for c in sorted(v["companies"], key=lambda c: -(c.get("cap") or 0)) if c.get("industry")][:RENAME_TOP]
                top_ind = Counter(plain_industry(c["industry"]) for c in big).most_common(1)
                head_ = (re.findall(r"[A-Za-z][A-Za-z-]{2,}", top_ind[0][0]) or [""])[-1].lower() if top_ind else ""
                from .theme_changes import first_sentence
                # the lines a deck prints of them: the map's line of their own words, else their description's first sentence
                lines_ = [own_words(one_line(c.get("what") or first_sentence(evidence(c.get("ticker")) if evidence else "")), c.get("name") or "")
                          for c in big]
                word_ = ""
                if top_ind and top_ind[0][1] * 2 > len(big) and head_ and sum(1 for t in lines_ if says_name(head_, [t])) * 2 >= len(big):
                    word_ = head_                 # the industry's own noun, which most of their lines say ("bank")
                elif lines_ and lines_[0]:
                    # else the word of the largest company's line that the theme's own name says ("Boeing is among the largest global
                    # aerospace manufacturers"), so the name keeps the map's meaning and says what they say
                    tw_ = {_name_stem(w) for w in re.findall(r"[a-z]{4,}", str(theme).lower())}
                    word_ = next((w for w in re.findall(r"[a-z]{4,}", lines_[0].lower()) if _name_stem(w) in tw_ and w not in NAME_GENERIC), "")
                if word_:
                    # r58 (the owner's open items on the live R57.2 Aerospace deck: "Commercial airframe integration (aircraft)", a word
                    # bolted on): the word of the name none of its companies say gives way to theirs, in place ("Commercial aircraft
                    # integration"); the word in brackets only when no single word of the name is the unsaid one
                    new_ = in_place_name(shown_, word_, texts_)
                    if not new_ or not says_name(new_, texts_):
                        new_ = f"{shown_} ({word_})"
                    if says_name(new_, texts_):
                        rows.append({"layer": shown_, "renamed": new_, "why": f"none of its companies' own words, industries or names say a word of "
                                                                             f"“{shown_}”; most of its largest companies are filed under {top_ind[0][0]}"})
                        for x in [v] + twins:
                            x["layer"] = new_ + x["layer"][len(shown_):]
                            x["aka"] = list(dict.fromkeys((x.get("aka") or []) + [shown_]))
                            if x.get("sibling"):
                                x["sibling"] = new_ + str(x["sibling"])[len(shown_):]
                            if isinstance(x.get("model"), dict) and x["model"].get("line"):        # its line names the other half
                                x["model"] = {**x["model"], "line": str(x["model"]["line"]).replace(f"“{shown_} (", f"“{new_} (")}
        if v.get("official") or v.get("scale") or not (v.get("by_model") or v.get("by_place") or v.get("industry_group")) or not v.get("companies"):
            continue
        name = _HALF_RX.sub("", v.get("layer") or "")
        texts = [own_text(evidence(c.get("ticker")) if evidence else c.get("what") or "") or (c.get("what") or "") for c in v["companies"]]
        inds = [c.get("industry") for c in v["companies"]]
        worded = [t for t in texts if len(t.strip()) >= 40]
        # a way of earning's own label ("Makers of their own products", "Lenders") names how they earn, which their models show; only a
        # label naming kinds of business (MODEL_KINDS), or a name a placement answer proposed, is said by what the members' words are
        kinded = labels.get(name) in MODEL_KINDS if v.get("by_model") else bool(v.get("by_place"))
        fits = not kinded or any(shares_vocabulary(name, t, i) for t, i in zip(texts, inds))
        # r582 (R58.2, the release gate on the live R58.1 Textiles input: "Resale and distribution", made by how its companies earn, holding
        # Vedant Fashions and Bizotic, neither of whose own words, industries or names says resale or distribution; Bizotic's say "ready-made
        # garments under the brand name ..., a men's apparel brand"): a layer named by a way of earning whose name has words of its own that
        # none of its companies' own words or industries share sends each company whose own words say another layer's name to the layer of two
        # or more whose name they say the most of; the others stay (a layer left with one company is single_layers' case)
        # (read as words_support reads a name: a word of how a business earns, "distribution", is a word of it)
        # (any word of the name of four letters or more said counts: "trading" in a company's words says "Distribution and trading")
        name_ws = [w for w in re.findall(r"[a-z]{4,}", name.lower()) if w not in ("other", "companies", "their", "makers", "products")]
        said_any = lambda t: any(re.search(r"\b" + re.escape(w[:max(4, len(w) - 3)]), t, re.I) for w in name_ws)      # noqa: E731
        if v.get("by_model") and not kinded and worded and layer_words(name) and name_ws \
                and not any(said_any(f"{t} {i or ''} {c.get('name') or ''}") or words_support(name, f"{t} {i or ''} {c.get('name') or ''}", theme)
                            for t, i, c in zip(texts, inds, v["companies"])):
            tw_ = kind_stems(theme)
            homes_ = [w for w in vc if w is not v and not w.get("official") and not w.get("by_model") and len(w.get("companies") or []) >= 2]
            stay_ = []
            for c, t in zip(v["companies"], texts):
                said_ = [w for w in homes_ if t.strip() and layer_says(w, t, tw_)[1] and prints_layer(w, t, c.get("name") or "")]
                if said_:
                    n_ = {id(w): said_count(w, t, tw_) for w in said_}
                    said_ = [w for w in said_ if n_[id(w)] == max(n_.values())]
                if len({_HALF_RX.sub("", w["layer"]) for w in said_}) != 1:
                    stay_.append(c)
                    continue
                to_ = _HALF_RX.sub("", said_[0]["layer"])
                why_ = f"none of “{name}”'s companies' own words or industries say what it names; its own words say what “{to_}” is"
                said_[0]["companies"] = list(said_[0]["companies"]) + [{**c, "moved": True, "refit": {"from": name, "to": to_, "why": why_}}]
                rows.append({"layer": name, "ticker": c.get("ticker"), "moved_to": to_, "why": why_})
            # the others: a layer named by what none of its companies' own words say is not made; each goes to "Other", with why
            if stay_:
                undo.append((v, f"none of “{name}”'s companies' own words or industries say what it names, and no other layer's name is said "
                                f"by its own words more than any other's", stay_))
            v["companies"] = []
            continue
        # r60 (LIVE9A-006): a layer named by its way of earning whose name is one kind of it (MODEL_KINDS) that fewer than half of its
        # companies' own words say, while more than half say another kind of it, takes that kind's name ("Oil, gas and mineral royalty
        # owners" for royalty trusts, never "Designs licensed for royalties")
        kinds_ = MODEL_KINDS.get(labels.get(name, "")) or ()
        mine_ = next((rx for nm_, rx in kinds_ if nm_ == name), None)
        if worded and fits and mine_ and sum(1 for t in texts if re.search(mine_, t or "", re.I)) * 2 < len(texts):
            other_ = [(nm_, sum(1 for t in texts if re.search(rx, t or "", re.I))) for nm_, rx in kinds_ if nm_ != name]
            best_ = max(other_, key=lambda x: x[1], default=("", 0))
            if best_[1] * 2 > len(texts):
                v["layer"] = best_[0] + v["layer"][len(name):]
                v["aka"] = list(dict.fromkeys((v.get("aka") or []) + [name]))
                v["named_by"] = "members"
                rows.append({"layer": name, "renamed": best_[0], "why": f"fewer than half of its companies' own words say what “{name}” names; "
                                                                         f"more than half say “{best_[0]}”"})
                continue
        if worded and not fits:
            new = kinds_name(labels.get(name, ""), texts)
            if new:
                v["layer"] = new
                v["aka"] = list(dict.fromkeys((v.get("aka") or []) + [name]))
                v["named_by"] = "members"
                rows.append({"layer": name, "renamed": new, "why": f"none of its companies' own words or industries say what “{name}” names; "
                                                                    f"their own words say “{new}”"})
                continue
            # r571 (the live R57 Consumer retail deck: "Single-category specialty retailers", 9 companies in R56, renamed by an answer to
            # "Niche specialty and category retailers" and then not made, all to "Other"): a layer the published version had under any of
            # its names is no new layer: it keeps its published name (the guard restored it), never undone
            known = [n for n in ([v.get("was") or ""] + list(v.get("aka") or [])) if n and _HALF_RX.sub("", n) in pub]
            if not known:                    # ...or by its companies: most of them were in one named layer of the published version
                from collections import Counter
                were = Counter(_HALF_RX.sub("", str((published or {}).get(c.get("ticker")) or "")) for c in v["companies"])
                top = were.most_common(1)[0] if were else ("", 0)
                if top[0] and not top[0].startswith("Other ") and top[1] * 2 > len(v["companies"]):
                    known = [top[0]]
            if known:
                if _HALF_RX.sub("", known[0]) != name:
                    rows.append({"layer": name, "renamed": _HALF_RX.sub("", known[0]),
                                 "why": f"none of its companies' own words say what “{name}” names; the name it had in the published version stays"})
                    v["layer"] = _HALF_RX.sub("", known[0]) + v["layer"][len(name):]
                    v["aka"] = list(dict.fromkeys((v.get("aka") or []) + [name]))
                continue
            if name not in pub:
                undo.append((v, f"none of its companies' own words or industries say what “{name}” names"))
                continue
        if len(v["companies"]) <= CONTRACT_SINGLE and v.get("by_model") and labels.get(name) == "holding":
            # r571 (the live R57 Medical devices deck: "Diversified groups", two holding companies): groups of other businesses are no
            # layer of a theme, published or not
            undo.append((v, f"a layer of {len(v['companies'])} groups of several businesses (“{name}”)"))
        elif len(v["companies"]) <= CONTRACT_SINGLE and name not in pub and not v.get("aka"):
            undo.append((v, f"a layer of one company a rule would make (“{name}”), new to the published version"))
    if not undo:
        return vc, rows
    by_name: dict = {}
    for v in vc:
        if not v.get("official") and all(v is not u[0] for u in undo):
            for nm in _names(v):
                by_name.setdefault(nm, v)
    rest_v = next((v for v in vc if other(v)), None)
    for v, why, *only in undo:
        name = _HALF_RX.sub("", v.get("layer") or "")
        for c in (only[0] if only else v["companies"]):
            lay = _HALF_RX.sub("", str((published or {}).get(c.get("ticker")) or ""))
            dest = by_name.get(lay) if lay and not lay.startswith("Other ") else None
            if dest is None:
                if rest_v is None:
                    rest_v = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                    vc = vc + [rest_v]
                dest = rest_v
            moved = {**{k: x for k, x in c.items() if k not in ("single", "fit", "placed_by", "sold_by")}, "moved": True,
                     "refit": {"from": name, "to": "" if dest is rest_v else _HALF_RX.sub("", dest.get("layer") or ""), "why": why + ": not made"}}
            dest["companies"] = list(dest["companies"]) + [moved]
        rows.append({"layer": name, "undone": len(only[0] if only else v["companies"]), "why": why})
        v["companies"] = []
    return [v for v in vc if v.get("companies") or not (v.get("by_model") or v.get("by_place") or v.get("industry_group") or v.get("official"))], rows


# v55 (R55, the owner's review of the live R54 Biotech deck: Merck & Co, about $65 bn of sales a year, shown under "Pipeline-stage and royalty-
# funded drug developers", left out of its figures but displayed there): a company's stage, commercial (a revenue business with products on
# sale) or development (clinical-stage, pre-revenue), decides which of a map's stage-defined layers it is displayed in. A layer whose name
# states a development stage holds no commercial-stage company, a layer whose name states commercial scale holds no development-stage one.
COMMERCIAL_LAYER = r"\bcommercial\b|\blarge\b|\bbig\b|\bestablished\b|\bportfolios?\b|\bmarketed\b|\bmajor\b|\bmature\b"
COMMERCIAL_SAYS = (r"\blargest\b[^.;]{0,80}\bby (?:revenue|sales)\b|\b(?:largest|biggest) (?:\w+ ){0,2}(?:pharmaceutical|biopharmaceutical|drug|"
                   r"biotech\w*|biomedical|medical) compan|\bproducts? (?:are|is) (?:marketed|sold) in\b|\bprimary products are\b|\bmarketed products\b|"
                   r"\bapproved (?:products|medicines|drugs|therapies)\b|\bproduct sales\b|\bcommercial[- ]stage\b|\bglobal commercial\b|"
                   r"\bportfolio of (?:marketed |approved |branded )?(?:products|medicines|drugs)\b|\bsells? (?:its )?(?:products|medicines|drugs) in\b")
DEVELOPMENT_SAYS = (r"\bclinical[- ]stage\b|\bpre-?revenue\b|\bdevelopment[- ]stage\b|\bpre-?clinical[- ]stage\b|\bproduct candidates?\b|"
                    r"\bdrug candidates?\b|\blead (?:product )?candidates?\b|\bno (?:approved )?products? (?:on (?:the )?market|approved)\b")
STAGE_FACTOR = 10.0             # v55: revenue this many times the development layer's median developer's, with an operating profit: commercial


def layer_stage(v: dict) -> str:
    """v55: "development" for a layer whose name (or the map's name for it) states a development stage or early-stage work (theme_data.
    PRE_REVENUE, EARLY_WORK), "commercial" for one whose name states commercial scale (COMMERCIAL_LAYER), else ""."""
    from .theme_data import EARLY_WORK, PRE_REVENUE
    name = f"{v.get('layer') or ''} {v.get('was') or ''}"
    if v.get("official"):
        return ""
    dev = bool(re.search(PRE_REVENUE, name, re.I) or re.search(EARLY_WORK, name, re.I))
    com = bool(re.search(COMMERCIAL_LAYER, name, re.I) and re.search(r"pharma|biotech|drug|medicine|therap", name, re.I))
    # a name (or the map's name for it) that states both stages ("Specialty and clinical-stage biotechs", the map's "Commercial specialty
    # biotechs") is of neither alone: it holds both
    return "development" if dev and not com else "commercial" if com and not dev else ""


def company_stage(words: str, revenue=None, ebitda=None, developers_median=None) -> tuple[str, str]:
    """v55: (stage, what shows it) of a company from its own evidence: "commercial" when its words state a revenue business with products on
    sale (COMMERCIAL_SAYS) and no development stage, or its revenue is STAGE_FACTOR times the developers' median or more with an operating
    profit; "development" when its words state a development stage (DEVELOPMENT_SAYS) and nothing commercial; ("", "") else."""
    t = str(words or "")
    com, dev = re.search(COMMERCIAL_SAYS, t, re.I), re.search(DEVELOPMENT_SAYS, t, re.I)
    if com and not dev:
        return "commercial", f"its own words: “{com.group(0)}”"
    if revenue and developers_median and revenue >= STAGE_FACTOR * developers_median and (ebitda or 0) > 0 and not dev:
        return "commercial", (f"revenue {STAGE_FACTOR:g} times the layer's median developer's or more, with an operating profit "
                              f"(EBITDA margin {ebitda:.1f}%)")
    if dev and not com:
        return "development", f"its own words: “{dev.group(0)}”"
    return "", ""


def stage_moves(vc: list[dict], words_of, theme: str, facts_of=None) -> tuple[list[dict], int]:
    """v55 (R55): (the layers, how many companies moved) with each company of a stage-defined layer (layer_stage) whose own stage (company_stage:
    its own words, else its stored revenue against the layer's developers') is the other displayed in the map's layer of its own stage, the
    largest one (its half by market value when that layer is split), else in "Other", with why ("refit", "stage"). `words_of(symbol)` its own
    words, `facts_of(symbol)` its stored facts ({"revenue", "ebitda"} when kept)."""
    staged = {k: [v for v in vc if layer_stage(v) == k] for k in ("development", "commercial")}
    if not staged["development"] and not staged["commercial"]:
        return vc, 0
    moves = []
    for v in vc:
        mine = layer_stage(v)
        if not mine:
            continue
        cos = v.get("companies") or []
        figs = {c.get("ticker"): (facts_of(c.get("ticker")) if facts_of else None) or {} for c in cos}
        young = sorted(f["revenue"] for f in figs.values() if (f.get("revenue") or 0) > 0 and f.get("ebitda") is not None and f["ebitda"] <= 0)
        mid = young[len(young) // 2] if len(young) >= 2 and mine == "development" else None
        for c in cos:
            f = figs.get(c.get("ticker")) or {}
            st, why = company_stage(words_of(c.get("ticker")) or c.get("what") or "", f.get("revenue"), f.get("ebitda"), mid)
            if st and st != mine:
                moves.append((v, c, st, why))
    if not moves:
        return vc, 0
    out = [dict(v, companies=list(v.get("companies") or [])) for v in vc]
    ids = {id(v): i for i, v in enumerate(vc)}
    other = next((v for v in out if v.get("official") and v.get("basis") == "rest"), None)
    drop = ("unfit", "unfit_why", "on_industry", "by_words", "own_goods", "refit", "sold_by", "fit")
    for v, c, st, why in moves:
        homes = [x for x in out if layer_stage(x) == st and x.get("companies")]
        if homes:
            base = max({_HALF_RX.sub("", x["layer"]) for x in homes}, key=lambda n: sum(len(x["companies"]) for x in homes if _HALF_RX.sub("", x["layer"]) == n))
            halves = [x for x in homes if _HALF_RX.sub("", x["layer"]) == base]
            dest = halves[0]
            if len(halves) == 2:
                big = next((x for x in halves if x["layer"].endswith("(larger)")), halves[0])
                floor = min((x.get("cap") or 0) for x in big["companies"]) if big["companies"] else 0
                dest = big if (c.get("cap") or 0) >= floor else next(x for x in halves if x is not big)
        else:
            if other is None:
                other = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                out.append(other)
            dest = other
        src = out[ids[id(v)]]
        src["companies"] = [x for x in src["companies"] if x is not c]
        frm, to = _HALF_RX.sub("", v["layer"]), ("" if dest is other else _HALF_RX.sub("", dest["layer"]))
        stage_said = {"commercial": "it is a commercial-stage company, a revenue business with products on sale",
                      "development": "it is a development-stage company, its products not yet on sale"}[st]
        named_by = {"commercial": "a development stage", "development": "commercial scale"}[st]
        moved = {**{k: x for k, x in c.items() if k not in drop}, "moved": True,
                 **({"fit": True} if dest is not other else {}),
                 "refit": {"from": frm, "to": to, "stage": st,
                           "why": f"{stage_said} ({why}), and “{frm}” is named by {named_by}"
                                  + ("" if to else "; no layer of the map is of its stage")}}
        dest["companies"] = sorted(dest["companies"] + [moved], key=lambda x: (-(x.get("cap") or 0), x.get("ticker") or ""))
    return [v for v in out if v.get("companies") or not v.get("official")], len(moves)


# v55 (R55, the owner's review of the live R54 Medical devices deck: UFP Technologies, a custom manufacturer of components for medical devices,
# out of "Surgical robotics systems" but left in an unexplained "Other"): a company of the theme whose business is a recognised adjacent kind
# (a contract manufacturer of the theme's products, a supplier of their components) that fits none of the map's layers goes to a layer of
# that kind named from the theme's own words when FALLBACK_MIN or more such companies are left, else stays in "Other" with that said
FALLBACK_KINDS = (("contract", r"\bcontract (?:development and )?manufactur\w*|\bcustom manufactur\w*|\bcontract mak\w*|\bcdmos?\b|\bcmos?\b|"
                               r"\boutsourced manufactur\w*|\bmanufacturing services\b|\bprivate[- ]label manufactur\w*|\bthird[- ]party manufactur\w*"),
                  ("components", r"\bcomponents?\b|\bsub-?assembl\w*|\bpackaging and delivery systems\b|\bdelivery systems?\b|\bparts\b"))
FALLBACK_MIN = 2
FALLBACK_NAMES = {frozenset({"contract"}): "contract manufacturers", frozenset({"components"}): "component suppliers",
                  frozenset({"contract", "components"}): "contract manufacturers and component suppliers"}


def fallback_kind(words: str, theme_words: set) -> str:
    """v55: "contract" or "components" when a company's own words say it makes the theme's products for others or supplies their components
    (FALLBACK_KINDS) in a sentence that names the theme's own product (`theme_words`); "" else."""
    from .theme_data import business_sentence, does_the_work
    part = business_sentence(str(words or ""))        # its principal business: the sentence of what it does now, never its group's or history
    for kind, rx in FALLBACK_KINDS:
        if part and re.search(rx, part, re.I) and does_the_work(part, theme_words):
            return kind
    return ""


def fallback_layer(vc: list[dict], words_of, theme: str) -> tuple[list[dict], dict | None]:
    """v55 (R55): (the layers, the fallback made or said: {"layer", "kinds", "symbols"} or {"line", "symbols"}) with the companies of "Other"
    whose own words make them contract manufacturers or component suppliers of the theme's products (fallback_kind) moved to one layer of
    that kind, named from the theme's own words ("Medical device contract manufacturers and component suppliers"), when FALLBACK_MIN or more
    are left and no layer of the map is of that kind already; fewer stay in "Other", each with that said ("fallback")."""
    other = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    if other is None:
        return vc, None
    tw = {w for w in kind_stems(theme)} - _HOW_STEMS
    found = [(c, k) for c in other.get("companies") or [] if not c.get("unread") for k in [fallback_kind(words_of(c.get("ticker")) or c.get("what") or "", tw)] if k]
    if not found:
        return vc, None
    kinds = frozenset(k for _, k in found)
    # a layer of the map already of that kind: those companies are its, by its own name (the map's placement and split decide that)
    if any(not v.get("official") and re.search(r"\bcontract\b|\bcustom\b|\bcomponents?\b|\bparts\b|\bcdmos?\b|\bcmos?\b|\bems\b|\boutsourc|"
                                               r"\bsubcontract|\bsuppliers?\b", f"{v.get('layer') or ''} {v.get('was') or ''}", re.I) for v in vc):
        return vc, None
    noun = re.sub(r"\s*\([^)]*\)", "", other_label(theme)[len("Other "):-len(" companies")]).strip()
    name = f"{noun[:1].upper()}{noun[1:]} {FALLBACK_NAMES[kinds]}"
    syms = [c.get("ticker") for c, _ in found]
    if len(found) < FALLBACK_MIN:
        said = (f"its own words make it one of the theme's {FALLBACK_NAMES[kinds]}, an adjacent kind of business; too few such companies "
                f"({len(found)}) for a layer of their own, so it is in “{other['layer']}”")
        out = [dict(v, companies=[{**c, "fallback": said} if c.get("ticker") in syms else c for c in v.get("companies") or []]) if v is other else v
               for v in vc]
        return out, {"line": said, "symbols": syms}
    layer = {"layer": name, "description": f"These companies make the theme's products for other companies, or supply their components, "
                                           f"by their own words; an adjacent kind of business beside the makers the map's layers name.",
             "by_place": True, "fallback": sorted(kinds),
             "companies": [{**{x: y for x, y in c.items() if x not in ("unfit", "unfit_why", "on_industry", "by_words", "own_goods")}, "fit": True,
                            "moved": True, "refit": {"from": (c.get("refit") or {}).get("from") or other["layer"], "to": name, "fallback": k,
                                                     "why": f"its own words make it one of the theme's {FALLBACK_NAMES[frozenset({k})]}, "
                                                            "an adjacent kind of business no layer of the map names"}}
                           for c, k in found]}
    out = []
    for v in vc:
        if v is other:
            rest = [c for c in v.get("companies") or [] if c.get("ticker") not in syms]
            out.append(layer)
            if rest:
                out.append({**v, "companies": rest})
            continue
        out.append(v)
    return out, {"layer": name, "kinds": sorted(kinds), "symbols": syms}


def _no_single_layers(out: list[dict], before: dict, main, fam, theme: str, fits=None) -> list[dict]:
    """The layers with none of one company that the split made or reshaped (R27): its company joins the largest other layer of its own family,
    else the theme's "Other" group (made when there is none), marked "single". R39 (lane s1-fit): the company of a layer the split made
    joins only a layer of its family it fits (`fits(company, layer)`: its own words share what that layer says is made or done)."""
    singles = [v for v in out if not v.get("official") and len(v["companies"]) == 1
               and (v.get("by_model") or id(v) not in before or {c.get("ticker") for c in v["companies"]} != before[id(v)])]
    if not singles:
        return out
    for v in singles:
        c = v["companies"][0]
        f = fam(c)
        same = [x for x in out if x is not v and x not in singles and not x.get("official") and x["companies"] and f and main(x["companies"]) == f
                and (fits is None or not v.get("by_model") or fits(c, x))]
        if same:
            target = max(same, key=lambda x: len(x["companies"]))
            target["companies"].append({**c, "moved": True, "single": True})
        else:
            other = next((x for x in out if x.get("official") and x.get("basis") == "rest"), None)
            if other is None:
                other = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                out.append(other)
            other["companies"].append({**c, "moved": True, "single": True, "fit": True})
        v["companies"] = []
    return [v for v in out if not (v in singles and v.get("by_model"))]


def names_signature(own: list[dict], by_layer: dict) -> str:
    """Which companies each of the map's layers holds once placed: the layer-name check is asked again only when this changes."""
    import hashlib
    parts = sorted(f"{v['layer']}:" + ",".join(sorted(c.get("ticker") or "" for c in list(v.get("companies") or []) + by_layer.get(v["layer"], [])))
                   for v in own)
    return hashlib.sha1("|".join(parts).encode(), usedforsecurity=False).hexdigest()[:16]


def _move(c: dict, frm: str, dest: dict, why: str, rows: list) -> None:
    """r60: a company moved by a rule into `dest`, with the reason (its marks of the layer it leaves dropped)."""
    to = _HALF_RX.sub("", dest.get("layer") or "") if not dest.get("official") else ""
    dest["companies"] = list(dest.get("companies") or []) + [{**{k: x for k, x in c.items() if k not in (
        "model_out", "out_why", "unfit", "sold_by", "kept_member", "held_published", "by_map", "line_says", "placed_by", "fit", "single")},
        "moved": True, "refit": {"from": frm, "to": to, "why": why}}]
    rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": frm, "to": to or str(dest.get("layer") or ""), "why": why})


def _whole_said(v: dict, text: str, name: str) -> bool:
    """r60: whether the line a deck prints of a company's words for a layer says a whole word of its name (its root with an ending:
    "brands" of "Branded", never "mission" of "missile") or its concept."""
    shown = _HALF_RX.sub("", v.get("layer") or "")
    line = layer_line("", text, name, shown, v.get("description") or "")
    if not line:
        return False
    roots = {re.sub(r"(?:ed|ing|ers?|s)$", "", w) if len(w) > 5 else w for w in layer_words(shown)}
    return any(re.search(r"\b" + re.escape(r) + r"(?:s|es|ed|ing|ers?)?\b", line, re.I) for r in roots if len(r) >= 3) \
        or bool(concept_said(shown, line, v.get("description") or ""))


def by_how_back(vc: list[dict], words_of, theme: str, published: dict | None = None) -> tuple[list[dict], list[dict]]:
    """r60 (R60, the live R59 Textiles deck: Vedant Fashions, "caters to the Indian celebration wear market with a diverse portfolio of
    brands", a published member of "Branded apparel companies", put by how it earns into "Resale and distribution", of which its own words
    say nothing): a company in a thin layer made by how companies earn (by_model, LISTED_MIN companies or fewer, never a half by market
    value) whose own words neither say nor
    print a line of it, but print a line of a layer the map named, goes to that layer: the one it is published in, else the one layer of two
    or more whose name its words say the most of. A way of earning read apart from its words never takes a company out of a layer its own
    words name. (the layers, a row for each company moved)."""
    tw, pub, rows = kind_stems(theme), published or {}, []
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    named = [v for v in vc if not v.get("official") and not v.get("by_model") and not v.get("by_place") and not v.get("industry_group")
             and v.get("companies") and not str(v.get("layer") or "").startswith("Other ")]
    # (a thin group only, of LISTED_MIN companies or fewer: a larger group by how its companies earn rests on that way of earning, as
    # read for each, and its companies' other words never break it up)
    from .theme_check import MODELS
    holding_ = {x[1] for k, x in MODELS.items() if k == "holding"}      # a group of several businesses is by what its companies are, never by one
    for v in [x for x in vc if x.get("by_model") and not x.get("official") and not _HALF_RX.search(str(x.get("layer") or ""))
              and len(x.get("companies") or []) <= LISTED_MIN and _HALF_RX.sub("", x.get("layer") or "") not in holding_
              # (never a group named by the kinds its companies' own words say, MODEL_KINDS: "Hotels and resorts", "Restaurants and ...")
              and not any(k_[0].lower() in _HALF_RX.sub("", x.get("layer") or "").lower() for ks_ in MODEL_KINDS.values() for k_ in ks_)]:
        for c in list(v.get("companies") or []):
            t, nm = own_text((words_of(c.get("ticker")) if words_of else None) or ""), c.get("name") or ""
            if not t.strip() or no_words(t) or prints_layer(v, t, nm) or layer_says(v, without_name(t, nm), tw)[1]:
                continue
            said = [w for w in named if prints_layer(w, t, nm) and _whole_said(w, t, nm)]
            home = [w for w in said if shown(w) == _HALF_RX.sub("", str(pub.get(c.get("ticker")) or ""))]
            if len(home) > 1:          # a layer halved by market value: the half of its size
                big = next((w for w in home if w.get("scale") == "larger" or str(w.get("layer")).endswith("(larger)")), home[0])
                floor = min((x.get("cap") or 0) for x in big.get("companies") or [{}])
                home = [big if (c.get("cap") or 0) >= floor else next(w for w in home if w is not big)]
            if not home:
                said = [w for w in said if len(w.get("companies") or []) >= 2]
                if said:
                    n_ = {id(w): said_count(w, without_name(t, nm), tw) for w in said}
                    said = [w for w in said if n_[id(w)] == max(n_.values())]
                home = said if len({shown(w) for w in said}) == 1 else []
            if not home:
                continue
            line = layer_line("", t, nm, shown(home[0]), home[0].get("description") or "")
            v["companies"] = [x for x in v["companies"] if x is not c]
            _move(c, shown(v), home[0], f"its own words say what “{shown(home[0])}” is (“{line}”) and nothing of “{shown(v)}”, a group by how "
                                        f"its companies earn", rows)
    return [v for v in vc if v.get("companies") or not v.get("by_model")], rows


# r60 (R60, the owner's review of the live R59 Consumer retail deck: MINISO, "a Chinese retailer and variety store chain", in "Apparel and
# consumer brand owners"): a retail operating format is read apart from the ownership of a brand
_FORMAT_SELF = re.compile(r"\b(?:is|are|as)\s+(?:an?|the|one of the)\s+([^.;:]{0,80}?)\b(?:retailers?|retail (?:chains?|compan(?:y|ies))|"
                          r"store chains?|chains? of [^.;:]{0,40}?stores|operators? of [^.;:]{0,40}?stores)\b", re.I)
BRAND_LAYER = re.compile(r"\bbrand(?:s|ed)?\b", re.I)
FORMAT_LAYER = re.compile(r"\bretail(?:ers?)?\b|\bstores?\b|\bchains?\b|\bmerchants?\b|\bclubs?\b|\boutlets?\b", re.I)


def format_moves(vc: list[dict], words_of, theme: str) -> tuple[list[dict], list[dict]]:
    """r60 (R60, the owner's review of the live R59 Consumer retail deck, P1 "separate business roles from retail formats": MINISO, "a
    Chinese retailer and variety store chain", put with the apparel and consumer brand owners): a company in a layer of brand owners (its
    name says brands, not stores or retailers) whose own words say what it is is a retailer or a store chain runs a retail format, whether or
    not it owns its brand: it goes to the layer of retailers (two or more) whose name or concept its words say, in a line a deck prints, when
    one does more than any other (a concept said first: "variety store chain" of value retail). (the layers, a row for each company moved)."""
    tw, rows = kind_stems(theme), []
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    fmt = [w for w in vc if not w.get("official") and FORMAT_LAYER.search(f"{shown(w)} {w.get('was') or ''}")
           and not BRAND_LAYER.search(shown(w)) and len(w.get("companies") or []) >= 2]
    for v in vc:
        if v.get("official") or not BRAND_LAYER.search(shown(v)) or FORMAT_LAYER.search(shown(v)) or not fmt:
            continue
        for c in list(v.get("companies") or []):
            t, nm = own_text((words_of(c.get("ticker")) if words_of else None) or ""), c.get("name") or ""
            said_is = _FORMAT_SELF.search(without_name(t, nm)) if t.strip() else None
            if not said_is:
                continue
            # a layer whose concept its words say first ("variety store chain" of value retail: what it is, even in an encyclopedia's
            # opening line no deck prints as its line), else one whose name its printed line says
            homes = [w for w in fmt if concept_said(shown(w), without_name(t, nm), w.get("description") or "")] or \
                [w for w in fmt if prints_layer(w, t, nm)]
            if len(homes) > 1:
                n_ = {id(w): said_count(w, without_name(t, nm), tw) for w in homes}
                homes = [w for w in homes if n_[id(w)] == max(n_.values())]
            if len(homes) != 1:
                continue
            bare_ = without_name(t, nm)
            hit_ = concept_said(shown(homes[0]), bare_, homes[0].get("description") or "")
            quote = bare_[said_is.start():hit_.end()] if hit_ and 0 <= hit_.start() - said_is.start() <= 120 else said_is.group(0)
            v["companies"] = [x for x in v["companies"] if x is not c]
            _move(c, shown(v), homes[0], f"its own words say it runs a retail format (“{' '.join(quote.split())}”): placed by its stores in "
                                         f"“{shown(homes[0])}”, not with the brand owners, whether or not it owns its brand", rows)
    return [v for v in vc if v.get("companies") or not (v.get("by_model") or v.get("by_place"))], rows


# r60 (R60, the owner's review of the live R59 Biotech deck: Merck and Johnson & Johnson summarised with commercial-stage biotechs): in a
# theme whose name says one kind of business, the kind beside it that its companies' own words may call them first, and the layer they make
# (name, description). A reviewed table of kinds of business, never a company's or a theme's name
SIBLING_KINDS = ((r"\bbiotech", r"(?<![a-z])pharmaceutical\b", r"\bbio\w*",
                  "Established pharmaceutical companies",
                  "Companies whose own words call them pharmaceutical companies first, not biotechnology or biopharmaceutical ones: drug makers "
                  "with marketed portfolios, often across several segments, said apart from the theme's commercial biotechs by their own words."),)


def kind_apart(vc: list[dict], words_of, theme: str) -> tuple[list[dict], list[dict]]:
    """r60 (R60, the owner's review of the live R59 Biotech deck, P1: established diversified pharmaceutical companies, Merck and Johnson &
    Johnson, "summarised with commercial biotech" in "Large commercial biotechs"): in a theme whose name says a kind (SIBLING_KINDS), the
    companies of a commercial-stage layer of that kind whose own words call them first a company of the kind beside it ("an American
    multinational pharmaceutical company", never a biopharmaceutical one) are of another operating model: they make a layer of their own
    (two or more, the layer they leave keeping two or more), so no figure of the theme's kind is summarised with theirs; the reason printed.
    (the layers, a row for each company moved)."""
    rows = []
    shown = lambda v: _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    for theme_rx, kind_rx, own_rx, name, desc in SIBLING_KINDS:
        if not re.search(theme_rx, str(theme or ""), re.I):
            continue
        # (never a layer whose own name already names the kind beside the theme's: "Large pharma and biotech portfolios")
        for v in [x for x in vc if not x.get("official") and layer_stage(x) == "commercial"
                  and re.search(theme_rx, f"{shown(x)} {x.get('was') or ''}", re.I)
                  and not re.search(r"\bpharma", f"{shown(x)} {x.get('was') or ''}", re.I)]:
            picks = []
            for c in v.get("companies") or []:
                t = without_name(own_text((words_of(c.get("ticker")) if words_of else None) or ""), c.get("name") or "")
                m_ = _SELF.search(t) if t.strip() else None
                if not m_:
                    continue
                phrase = m_.group(1).lower()
                k, o = re.search(kind_rx, phrase), re.search(own_rx, phrase)
                if k and (o is None or k.start() < o.start()):
                    picks.append((c, m_.group(0).strip()))
            if len(picks) < 2 or len(v["companies"]) - len(picks) < 2:
                continue
            dest = next((x for x in vc if shown(x) == name), None)
            if dest is None:
                dest = {"layer": name, "description": desc, "by_place": True, "kind_apart": True, "companies": []}
                vc = vc + [dest]
            for c, said_ in picks:
                v["companies"] = [x for x in v["companies"] if x is not c]
                _move(c, shown(v), dest, f"its own words call it a company of another kind than the theme's (“{said_}”): an established "
                                         f"drug maker, said apart from “{shown(v)}”", rows)
    return vc, rows


LISTED_MIN = 4                  # r59: a layer of this many companies or more is never mostly listed and left out of its figures (deck_check LEFT_MIN)
_OUT_SAID = {"other": "it earns another way than the layer's companies", "unknown": "its evidence doesn't show how it earns"}


# r62 (the owner's review of the live R60 Regional banks deck, P1: Capital One, a US bank, in "Foreign banking groups earning loan interest"):
# a layer whose own name or description says its companies are foreign to the theme's market, and the filing forms that say where a
# company files from: a US domestic filer's own reports (10-K, 10-Q, 8-K) against a foreign private issuer's (20-F, 40-F, 6-K) (a company
# with no SEC filings stored, an Indian listing among them, is never moved by it)
FOREIGN_LAYER = re.compile(r"\bforeign\b|\bnon-?(?:us|u\.s\.|american|indian)\b|\boverseas\b|\boutside (?:the )?(?:us|united states|india)\b", re.I)
HOME_FORMS = re.compile(r"\((?:10-K|10-Q|8-K)\)")         # a US domestic filer's own reports, as its stored filings' titles name them
ABROAD_FORMS = re.compile(r"\((?:20-F|40-F|6-K)\)")        # a foreign private issuer's


def domicile_moves(vc: list[dict], facts_for) -> tuple[list[dict], list[dict]]:
    """r62: a company in a layer whose name (or its description's first sentence) says its companies are foreign to the theme's market
    (FOREIGN_LAYER), whose stored filings are a domestic filer's own (HOME_FORMS, none of ABROAD_FORMS), is not foreign: it goes to the
    named layer of its official industry whose companies' median market value is nearest its own, else to the theme's "Other" group, with
    the reason. (the layers, a row for each company moved)."""
    home, abroad = HOME_FORMS, ABROAD_FORMS
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    first = lambda t: re.split(r"(?<=[.;])\s", str(t or ""), maxsplit=1)[0]       # noqa: E731
    foreign = [v for v in vc if not v.get("official") and v.get("companies")
               and (FOREIGN_LAYER.search(_HALF_RX.sub("", v.get("layer") or "")) or FOREIGN_LAYER.search(first(v.get("description"))))]
    if not foreign:
        return vc, []
    homes = [v for v in vc if not v.get("official") and v.get("companies") and v not in foreign
             and not str(v.get("layer") or "").startswith("Other ")]
    rows = []
    for v in foreign:
        keep = []
        for c in v["companies"]:
            try:
                filed = str((facts_for(c.get("ticker")) or {}).get("filings") or "")
            except Exception:
                filed = ""
            if not home.search(filed) or abroad.search(filed):
                keep.append(c)
                continue
            ind = key(c.get("industry"))
            cap = c.get("cap") or 0

            def gap(w, ind=ind, cap=cap):
                caps = sorted(x.get("cap") for x in w["companies"] if x.get("cap"))
                if not caps or not cap:
                    return float("inf")
                mid = caps[len(caps) // 2]
                return abs(math.log(cap) - math.log(mid))
            near = sorted((w for w in homes if ind and any(key(x.get("industry")) == ind for x in w["companies"])), key=lambda w: (gap(w), w.get("layer") or ""))
            dest = near[0] if near else rest_v
            if dest is None:
                keep.append(c)
                continue
            frm = _HALF_RX.sub("", v.get("layer") or "")
            to = "" if dest is rest_v else _HALF_RX.sub("", dest.get("layer") or "")
            why = (f"its own filings are a domestic filer's ({', '.join(sorted({x.strip('()') for x in home.findall(filed)}))}), so it is not one of “{frm}”"
                   + (f"; in the layer of its official industry whose companies' market values are nearest its own" if to else ""))
            dest["companies"] = list(dest["companies"]) + [{**{k: x for k, x in c.items() if k not in ("model_out", "out_why", "unfit", "line_says")},
                                                            "moved": True, "refit": {"from": frm, "to": to, "why": why, "domicile": True}}]
            rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": frm, "to": to, "why": why})
        v["companies"] = keep
    return [v for v in vc if v.get("companies") or v.get("official")], rows


def narrower_name(earlier: str, shown: str) -> bool:
    """e78 (the owner's review of the live R76 REITs deck: Essex Property Trust, an owner of apartment communities, kept in "Other" as "the last
    re-check moved it out" of "Residential landlords": that re-check had moved it out of the same layer under its earlier name, "Manufactured
    housing and RV communities"): whether a layer's earlier name names fewer kinds of property than the name it shows now (a kind the shown
    name names that the earlier one doesn't: layer_property_types), so a move out of it under that name is no finding on the layer as it is."""
    a, b = _HALF_RX.sub("", str(earlier or "")), _HALF_RX.sub("", str(shown or ""))
    if not a or a == b:
        return False
    ta, tb = layer_property_types(a), layer_property_types(b)
    return bool(ta) and bool(tb - ta)


def listed_out(vc: list[dict], words_of, theme: str, moved_before: dict | None = None, figures_of=None,
               published: dict | None = None) -> tuple[list[dict], list[dict]]:
    """r59 (R59, the live R58.2 decks: Media "Cable and satellite distribution" 3 of its 7 in its calculations, Oil and gas "Oilfield
    services and equipment makers" 4 of 9, Consumer retail "Resale, rental and small digital commerce" 2 of 5; JPMorgan Chase moved into
    "Card issuers and consumer lenders" and listed there with a line that says none of it; Medical devices "Diversified groups" of 2), after
    every rule:
    1. a named layer of LISTED_MIN or more most of whose companies are outside its figures (left out, or with no stored figure when
       `figures_of` is given): a company left out of its figures whose own words say the layer's work in a line a deck prints (prints_layer)
       and say a word of its name apart from the theme's (said_count) counts in them on those words ("by_words", its read set aside); one
       whose words, stored, neither print nor say a word of the layer's name (words_support, layer_words) is not listed in it: it goes to the theme's "Other" group with the reason. The layer keeps two companies or more;
    2. a company the last re-check moved into a layer (`moved_before`) that is listed there as another business, its words printing no line of
       the layer, goes back where it was, with the reason;
    3. a layer of groups of several businesses (by how they earn) left with CONTRACT_SINGLE companies or fewer is not made (truthful_layers'
       rule, after the rules that run later);
    and each company of a named layer whose words hold no line a deck can print of its layer is marked ("line_says": False), so the
    figures' window adds those whose lines do first (for_figures). (the layers, a row for each company moved)."""
    rest_v = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    if rest_v is None:
        return vc, []
    from .theme_check import MODELS
    before, rows = moved_before or {}, []
    labels = {x[1]: k for k, x in MODELS.items()}
    text_of = lambda c: own_text((words_of(c.get("ticker")) if words_of else None) or "")        # noqa: E731
    tw = kind_stems(theme)

    def says(t: str, nm: str, shown: str) -> bool:
        # a word of the layer's name in its words: one apart from the theme's (words_support), or, for a name of the theme's words only
        # ("Pharmaceuticals"), one of those
        bare = without_name(t, nm)
        return words_support(shown, bare, theme) or any(_line_says(bare, w) for w in layer_words(shown))
    out_of = lambda c: bool(c.get("model_out")) or isinstance(c.get("unfit"), dict)              # noqa: E731

    def no_fig(c) -> bool:
        if figures_of is None:
            return False
        try:
            f_ = figures_of(c.get("ticker")) or {}
            # r65e: a page read whose figures hold no revenue (a company before its first sale: theme_routes._figures_reader "read") has
            # its figures stored, and is in its layer's calculations on them (theme_data.calc_record)
            return not (f_.get("revenue") or f_.get("read"))
        except Exception:
            return False

    def go(c, frm: str, dest, why: str):
        moved = {**{k: x for k, x in c.items() if k not in ("model_out", "out_why", "unfit", "sold_by", "kept_member", "held_published",
                                                            "by_map", "line_says", "placed_by", "fit")},
                 "moved": True, "refit": {"from": frm, "to": "" if dest is rest_v else _HALF_RX.sub("", dest.get("layer") or ""), "why": why}}
        dest["companies"] = list(dest["companies"]) + [moved]
        rows.append({"ticker": c.get("ticker"), "name": c.get("name"), "from": frm, "to": moved["refit"]["to"], "why": why})

    named = [v for v in vc if not v.get("official") and not v.get("scale") and v.get("companies")
             and not str(v.get("layer") or "").startswith("Other ")]
    by_name = {nm: v for v in named for nm in ({_HALF_RX.sub("", v.get("layer") or ""), v.get("was") or ""} | set(v.get("aka") or [])) - {""}}
    caps_ = sorted(((c.get("cap") or 0, c.get("ticker")) for v in vc for c in v.get("companies") or [] if c.get("ticker")), key=lambda t: (-t[0], t[1]))
    top_ = {t for cap, t in caps_[:min(TOP_MEMBERS, len(caps_) // TOP_SHARE)] if cap}
    # r63e: the companies whose figures the dive reads (for_figures): every one the map named itself, then the largest
    window_ = {c.get("ticker") for v in vc if not v.get("official") for c in v.get("companies") or [] if not c.get("placed")} \
        | {t for _, t in caps_[:FIGURES_MAX]}
    for v in named:
        shown = _HALF_RX.sub("", v.get("layer") or "")
        names = ({shown, v.get("was") or ""} | set(v.get("aka") or [])) - {""}
        cos = list(v["companies"])
        # r60: also a layer holding a company the last re-check moved out of it (its change log's [this layer, elsewhere])
        # (never one of the theme's largest, TOP_MEMBERS: a re-check's move of one of them out of every layer is no evidence: Reliance)
        # (and only out of a layer the published version had: a move out of a layer that re-check lost, restored since, is no finding on words)
        had_ = any(_HALF_RX.sub("", str(x or "")) in names for x in (published or {}).values())
        # (and only a move the published version holds: the company is published where that re-check put it)
        left_of = lambda c: had_ and c.get("ticker") not in top_ and (lambda mb: isinstance(mb, (list, tuple)) and len(mb) == 2  # noqa: E731
                                                                      and mb[0] in names and mb[1] not in names
                                                                      and _HALF_RX.sub("", str((published or {}).get(c.get("ticker")) or "")) == _HALF_RX.sub("", str(mb[1] or ""))
                                                                      and not narrower_name(mb[0], shown)
                                                                      )(before.get(c.get("ticker")))
        if not any(out_of(c) or left_of(c) for c in cos):
            continue                       # (stored figures read only for a layer with a company left out)
        mostly = len(cos) >= LISTED_MIN and sum(1 for c in cos if out_of(c) or no_fig(c)) * 2 > len(cos)
        keep, gone = [], []
        for c in cos:
            t, nm = text_of(c), c.get("name") or ""
            # r62 (the live R60 decks' "left out>50%": US Steel and metals "Specialty alloys" 2 of 5 and "Aluminium" 2 of 8, Biotech 4 of 9,
            # Capital markets 7 of 18, members with no figure stored or no description of their own listed as the layer's and left out of
            # it): in a layer mostly left out of its figures, a member with no figure stored, or left out with no description of its own
            # stored, is not counted as the layer's: it is listed in the theme's "Other" group with that reason until it is read
            # r63e (the live R62 Biotech deck: 127 of 821 in informative layers against 549 on R60, the description-verified members of
            # "Specialty and clinical-stage biotechs" beyond the figures' window, none of them read for figures, sent to "Other"): a member
            # with no figure stored whose own words say the layer stays the layer's; a figure not read yet says nothing of membership
            # (one among the largest whose figures the dive reads, FIGURES_MAX, has had its figure looked for: no figure there is r62's case)
            # r65e (the live R64 Biotech deck: 400 of 821 in informative layers against 459 on R63, 69 members of "Specialty and
            # clinical-stage biotechs" sent to "Other" with no figure stored: members beyond the window, "a clinical-stage biopharmaceutical
            # company", whose words don't state how they earn, model_out "unknown"; and Erasca, Immunovant and Kodiak, among the largest,
            # whose pages were read and hold no revenue, no_fig's "read"): a member beyond the window whose own words say the layer is never
            # sent out by a figure not read, its way of earning read or not stated in them ("unknown"); the rules after this one decide its
            # place in the figures (one read as another business stays r62's case)
            said_ = bool(t.strip()) and not no_words(t) and (says(t, nm, shown) or prints_layer(v, t, nm))
            worded_ = c.get("ticker") not in window_ and said_ and (not out_of(c) or (c.get("model_out") == "unknown"
                                                                                    and not isinstance(c.get("unfit"), dict)))
            # e81 (the owner's review of the R79 decks, P0 "business classification apart from financial-data availability": Textiles'
            # Addi Industries and Davin Sons Retail sent out of "Garment contract manufacturers" for having no stored figures; IT services
            # 173 -> 166 of 252 in informative layers, Textiles 313 -> 304): a figure not stored says nothing of what a company does: it
            # keeps its layer, marked as having no figure for the layer's calculations ("fig_unread", out of them as any row with none);
            # only a member left out with no description of its own stored is listed in "Other" until it is read
            if mostly and not left_of(c) and out_of(c) and not isinstance(c.get("unfit"), dict) and (not t.strip() or no_words(t)) \
                    and not no_fig(c):
                gone.append((c, rest_v, f"listed in “{shown}” with no description of its own stored: not counted as the layer's until it is read"))
                continue
            if mostly and not left_of(c) and no_fig(c) and not worded_ \
                    and not (out_of(c) and t.strip() and not no_words(t) and not says(t, nm, shown)):
                keep.append({**c, "fig_unread": True, "no_figure": True})
                continue                     # (one left out whose own words say no word of the layer: the business rule below)
            if not out_of(c) and not left_of(c):
                # (r63e: one kept beyond the figures' window with no figure read is marked, so the window never adds it to fill a layer)
                keep.append({**c, "fig_unread": True} if mostly and worded_ and no_fig(c) else c)
                continue
            line = bool(t.strip()) and not no_words(t) and prints_layer(v, t, nm)
            mb = before.get(c.get("ticker"))
            came = mb[0] if isinstance(mb, (list, tuple)) and len(mb) == 2 and mb[1] in names and mb[0] not in names else None
            left = mb[1] if left_of(c) else None
            if mostly and line and c.get("model_out") and not isinstance(c.get("unfit"), dict) and said_count(v, t, tw):
                keep.append({**{k: x for k, x in c.items() if k not in ("model_out", "out_why")}, "by_words": True,
                             "words_over": c.get("model_out")})
            elif mostly and out_of(c) and not line and t.strip() and not no_words(t) and not says(t, nm, shown):
                # (one with no words of its own stored is where its official industry put it: nothing it says contradicts that)
                said = _OUT_SAID.get(c.get("model_out") or "", "its own words are of another business")
                # e82 (R80 Biotech, informative 505 -> 491: 37 clinical-stage companies, Editas, Allogene, Fate, Revolution Medicines ...,
                # sent to "Other" when the AI renamed "Specialty and clinical-stage biotechs" to "Commercial specialty biotechs", their words
                # saying "clinical-stage" of the theme's "Clinical-stage platform developers"): one whose words print a line of another
                # named layer and say a word of its name goes there, never to "Other"
                # (two words of its name or more, the theme's own aside: one shared word such as "developers" is no evidence)
                other_ = next((w for w in named if w is not v and not w.get("scale") and says(t, nm, _HALF_RX.sub("", w.get("layer") or ""))
                               and prints_layer(w, t, nm) and said_count(w, without_name(t, nm), tw) >= 2), None)
                if other_ is not None:
                    gone.append((c, other_, f"listed in “{shown}” but left out of its figures ({said}), and its own words say no word of its "
                                            f"name; they say what “{_HALF_RX.sub('', other_.get('layer') or '')}” is"))
                else:
                    gone.append((c, rest_v, f"listed in “{shown}” but left out of its figures ({said}), and its own words say no word of its "
                                            f"name: not listed in it"))
            elif came is not None and isinstance(c.get("unfit"), dict) and not line:
                back = by_name.get(_HALF_RX.sub("", came)) if came and not came.startswith("Other ") else None
                gone.append((c, back if back is not None and back is not v else rest_v,
                             f"its own words hold no line that says what “{shown}” is: not moved into it, it stays where it was"))
            elif left is not None and not line and (isinstance(c.get("unfit"), dict) or (t.strip() and not no_words(t) and not says(t, nm, shown))):
                # r60 (the R60 replay of the live R59 Logistics input: Aspinwall, which R59 moved out of "Freight forwarders and NVOCC agents"
                # on no line of its words, placed in it again by the next check, listed there as another business): one the last re-check
                # moved out of a layer whose words still hold no line of it stays where that re-check put it, never flipping back
                back = by_name.get(_HALF_RX.sub("", left)) if left and not left.startswith("Other ") else None
                gone.append((c, back if back is not None and back is not v else rest_v,
                             f"its own words hold no line that says what “{shown}” is: the last re-check moved it out of that layer, and it stays out"))
            else:
                keep.append(c)
        if mostly:                        # (r65e: one kept by its words beyond the window, however its way of earning was read, marked too)
            unread_ = {c.get("ticker") for c in cos if c.get("ticker") not in window_ and no_fig(c) and not left_of(c)
                       and (not out_of(c) or c.get("model_out") == "unknown")}
            keep = [{**c, "fig_unread": True} if c.get("ticker") in unread_ and not c.get("fig_unread") else c for c in keep]
        if gone and len(keep) < 2:
            keep, gone = cos, []          # a layer is never left with one company by this rule
        for c, dest, why in gone:
            go(c, shown, dest, why)
        v["companies"] = keep
    # r60 (the R60 replays of the live R59 inputs: IT services' Ekennis, "software IT Consulting Services ... and Printing", put from "Other"
    # into "Mid-tier digital engineering and cloud services", Athena Global into "Engineering R&D services", by how they earn, their words
    # saying nothing of either): a company placed by its words alone (never by the map or an answer) that this placement puts into a named
    # layer other than the one it is published in, by no check of its words, whose words neither print a line of it nor say a word of its name or concept,
    # stays where it is published (when its words print a line of that layer, or it is "Other")
    pub = published or {}
    for v in named:
        shown = _HALF_RX.sub("", v.get("layer") or "")
        names = ({shown, v.get("was") or ""} | set(v.get("aka") or [])) - {""}
        stay, back_ = [], []
        for c in v.get("companies") or []:
            was = _HALF_RX.sub("", str(pub.get(c.get("ticker")) or ""))
            t, nm = text_of(c), c.get("name") or ""
            ref_ = c.get("refit") if isinstance(c.get("refit"), dict) else {}
            # (only a placement no rule gave a reason of its words for: never one a rule restored, held or moved on its words; a move back by
            # what it sells, sold_what's, says nothing of its words for the layer it lands in)
            if not was or was in names or c.get("verified") or c.get("on_industry") or c.get("held") or c.get("kept_member") \
                    or c.get("placed") != "words" or c.get("sold_by") \
                    or c.get("restored") or c.get("held_published") or c.get("placed_by") or c.get("fallback") or (ref_ and not ref_.get("sold")) \
                    or not t.strip() or no_words(t) or prints_layer(v, t, nm) or says(t, nm, shown) or layer_says(v, without_name(t, nm), tw)[1]:
                stay.append(c)
                continue
            dest = rest_v if was.startswith("Other ") else by_name.get(was)
            if dest is None or dest is v or (dest is not rest_v and not prints_layer(dest, t, nm)):
                stay.append(c)
                continue
            back_.append((c, dest))
        if back_ and len(stay) >= 2:
            v["companies"] = stay
            for c, dest in back_:
                go(c, shown, dest, f"its own words say nothing of “{shown}”: not moved into it, it stays where it is published")
    # r62 (the R62 replays of the live R60 inputs: Tahmar Enterprises and Cupid Breweries, published in "Other", put into "Spirits brand owning
    # and bottling" by how they earn; Logprostyle into "Production homebuilding"; Array Digital Infrastructure into "Telecom operators";
    # Shivalik Rasayan into "Branded and generic crop protection"; Naga Dhunseri, an investment company, into "Microfinance and small-ticket
    # lenders"; each map pick's words, official industry and name saying no word of the layer): a company this placement puts into a named
    # layer other than the one it is published in, whose own words, official industry and name say no word of that layer's name or concept
    # (gate_says, the release gate's own reading), stays where it is published, with the reason (a market-value half too)
    for v in [w for w in vc if not w.get("official") and w.get("companies") and not str(w.get("layer") or "").startswith("Other ")]:
        shown = _HALF_RX.sub("", v.get("layer") or "")
        names = ({shown, v.get("was") or ""} | set(v.get("aka") or [])) - {""}
        stay, back_ = [], []
        for c in v.get("companies") or []:
            was = _HALF_RX.sub("", str(pub.get(c.get("ticker")) or ""))
            t = " ".join(str(x or "") for x in (text_of(c), c.get("what"), c.get("industry"), c.get("name")))
            rf_ = c.get("refit") if isinstance(c.get("refit"), dict) else {}
            # (the name it is shown under, as the gate reads it; never a move on the rule's own evidence: its revenue against the layer's
            # median, its stage, its filing forms, a quote of its own words the audit checked for the layer)
            if not was or was in names or gate_says(shown, t) is not False or rf_.get("scale") or rf_.get("stage") or rf_.get("domicile") \
                    or (rf_.get("quotes") or [""])[0]:
                stay.append(c)
                continue
            dest = rest_v if was.startswith("Other ") else by_name.get(was)
            if dest is None or dest is v:
                stay.append(c)
                continue
            back_.append((c, dest))
        if back_ and len(stay) >= 2:
            v["companies"] = stay
            for c, dest in back_:
                go(c, shown, dest, f"its own words, official industry and name say no word of “{shown}”: not moved into it, it stays where it "
                                   f"is published")
    for v in named:
        shown = _HALF_RX.sub("", v.get("layer") or "")
        if v.get("companies") and len(v["companies"]) <= CONTRACT_SINGLE and v.get("by_model") and labels.get(shown) == "holding":
            for c in v["companies"]:
                go(c, shown, rest_v, f"a layer of {len(v['companies'])} groups of several businesses (“{shown}”): not made")
            v["companies"] = []
    # r65e (the live R64 Fertilizers deck, p.23: "Specialty chemicals", a layer of one official industry, over Foseco, "products used in the
    # metallurgical industry", and DDev Plastiks, "Plastic Compounds", neither line saying chemical, once its member with no description of
    # its own was listed in "Other"): a layer made of one official industry none of whose companies' own words hold a line that says a word
    # of its name or concept (prints_layer; one of them at least has words of its own) is not made: the industry put them together, nothing
    # they say of their work does. Its companies are listed in the theme's "Other" group, still in the theme, with the reason
    for v in named:
        cos = v.get("companies") or []
        shown = _HALF_RX.sub("", v.get("layer") or "")
        if not v.get("industry_group") or not cos or not layer_words(shown):
            continue
        worded = [(text_of(c), c.get("name") or "") for c in cos]
        worded = [(t, n) for t, n in worded if t.strip() and not no_words(t)]
        if not worded or any(prints_layer(v, t, n) for t, n in worded):
            continue
        for c in cos:
            go(c, shown, rest_v, f"“{shown}” is made of its companies' official industry, and none of their own words says a word of its name: "
                                 f"listed in the theme's “Other” group")
        v["companies"] = []
    for v in named:
        if len(v.get("companies") or []) != 1:
            v.pop("single_kept", None)          # r60: kept as a layer of one company only while it holds one
        shown = _HALF_RX.sub("", v.get("layer") or "")
        marked = []
        for c in v.get("companies") or []:
            t = text_of(c)
            says = not t.strip() or no_words(t) or prints_layer(v, t, c.get("name") or "")
            marked.append({**c, "line_says": False} if not says else {k: x for k, x in c.items() if k != "line_says"})
        v["companies"] = marked
    return [v for v in vc if v.get("companies") or not (v.get("by_model") or v.get("by_place") or v.get("industry_group") or v.get("official"))
            or v is rest_v], rows


def for_figures(m: dict, cap: int = FIGURES_MAX) -> tuple[dict, dict]:
    """(the map the dive's figures, prices and news are worked out on, {"shown", "of"}): every company the AI named, then the largest of
    the rest of the base, `cap` in all at most (a theme of 500 drug makers is listed in full, its figures on the largest). Official
    layers left with no company are dropped."""
    # the companies the AI named itself; one placed in a layer after the map (place_rest) is base, by size like the rest
    named = {c["ticker"] for v in m.get("value_chain") or [] if not v.get("official") for c in v.get("companies") or [] if not c.get("placed")}
    named |= {c["ticker"] for s in m.get("sub_themes") or [] for c in s.get("companies") or []}
    rest = sorted({(c.get("cap") or 0, c["ticker"]) for v in m.get("value_chain") or [] for c in v.get("companies") or []
                   if (v.get("official") or c.get("placed")) and c["ticker"] not in named}, key=lambda x: (-x[0], x[1]))
    keep = named | {s for _, s in rest[:max(0, cap - len(named))]}
    # r582 (R58.2, the live R58.1 decks: "Payment networks and processors" printed with Block alone of its 7 companies, "Pharmaceuticals"
    # with one of its 27; "Distribution and trading" with Aptus Pharma alone once one of its two was merged as one company under two
    # symbols): a named layer the window holds fewer than WINDOW_LAYER_MIN companies of gains its next largest companies, up to that many,
    # those in the layer's figures first (its own words or industry keep them there); a few more figures read, never a layer printed alone
    for v in m.get("value_chain") or []:
        # (never a half by market value: a half the window shows too few of is undone into its layer, unsplit_unshown)
        if v.get("official") or v.get("scale") or _HALF_RX.search(str(v.get("layer") or "")) or str(v.get("layer") or "").startswith("Other "):
            continue
        cos = [c for c in v.get("companies") or [] if c.get("ticker")]
        inside = [c for c in cos if c["ticker"] in keep]
        if not inside or len(inside) >= WINDOW_LAYER_MIN or len(cos) <= len(inside):
            continue
        # r59 (the live R58.2 Pharma deck: CCME Global added to "Distribution and trading" with a line that says none of it): those
        # whose words hold a line of the layer come before those whose words hold none ("line_says", listed_out)
        more = sorted((c for c in cos if c["ticker"] not in keep and not c.get("fig_unread")),
                      key=lambda c: (bool(c.get("model_out") or c.get("unfit")), c.get("line_says") is False, -(c.get("cap") or 0), c["ticker"]))
        keep |= {c["ticker"] for c in more[:WINDOW_LAYER_MIN - len(inside)]}
    total = len(named | {s for _, s in rest})
    vc = []
    for v in m.get("value_chain") or []:
        cos = [c for c in v.get("companies") or [] if c["ticker"] in keep]
        if cos or not v.get("official"):
            vc.append({**v, "companies": cos})
    return {**m, "value_chain": vc}, {"shown": len(keep), "of": total}


def to_describe(m: dict, n: int = DESCRIBE_MAX) -> list[str]:
    """The base companies whose own one-line description the page shows (official layers, largest first), at most `n`."""
    rows = sorted({(c.get("cap") or 0, c["ticker"]) for v in m.get("value_chain") or [] for c in v.get("companies") or []
                   if v.get("official") or c.get("placed")}, key=lambda x: (-x[0], x[1]))
    return [s for _, s in rows[:n]]


# R35: a full stop after a legal form or an initial ends no sentence (live: "Qnity Electronics, Inc. is a major provider of materials..." was
# shown as "Qnity Electronics, Inc", and so were Marvell, Skyworks and four more; "the U.S. market")
_NOT_END = r"(?<![A-Z]\.)(?<!\bInc\.)(?<!\bINC\.)(?<!\bCorp\.)(?<!\bLtd\.)(?<!\bCo\.)(?<!\bPvt\.)(?<!\bNo\.)(?<!\bSt\.)(?<!\bDr\.)"
_FIRST = re.compile(r"^(.{20,240}?[.;])" + _NOT_END + r"(?:\s|$)")
# what a company's description says before its business (the owner, 7 Nov: "**Company Overview **", "Incorporatedin1994", "Business Overview:")
_MARKUP = re.compile(r"\*+|#+")
# (Release 63 CI: SPEL Semiconductor's profile glues "Holding Company: Natronix ..." onto its first sentence with no full stop, so its line ran
# on and was cut at "has its", no own words left; a holding-company or registered-office label a profile glues on ends the sentence before it)
_HEADING = re.compile(r"\s*\b(?:company|business|corporate)\s+(?:overview|profile|description)\s*:?|\s*\babout\s+(?:us|the\s+company)\s*:"
                      r"|\s+\b(?:(?:ultimate\s+)?holding|parent)\s+company\s*:|\s+\bregistered\s+office\s*:"
                      # r64e (LIVE11A-003: Deccan Cements "... wind sources Product Profile: a) Ordinary Portland Cement (OPC): ...")
                      r"|\s+\b(?:product|products|key\s+products?)\s+(?:profile|portfolio|range|mix)\s*:"
                      # fix20 (LIVE14A-003: Andhra Cements "...manufacturing and selling cement Corporate History & Ownership Changes Andhra
                      # Cements Limited has undergone ..."): a page's heading in title case run into the text before the next sentence
                      r"|\s+(?-i:(?:[A-Z][a-z]+\s+){0,2}(?:History|Overview|Background|Milestones|Timeline)(?:\s+(?:&|and)\s+[A-Z][a-z]+)*"
                      r"(?:\s+[A-Z][a-z]+)?)(?=\s+[A-Z])", re.I)
# R76 (CI: Sarda Proteins' "...deals in the trading of Solar Cells Business Overview: The co. historically dealt in protein and food products.
# In Sep 2024, it expanded ... solar-cell manufacturing ...", cut at "Business Overview:", left no own words and was read as a food company):
# own_words ends a line only at a page's title-case history heading run into it (Andhra Cements), never at the "Business Overview:" label a
# description opens its account with
_HEADING_RUN_IN = re.compile(r"\s+(?-i:(?:[A-Z][a-z]+\s+){0,2}(?:History|Overview|Background|Milestones|Timeline)(?:\s+(?:&|and)\s+[A-Z][a-z]+)*"
                             r"(?:\s+[A-Z][a-z]+)?)(?=\s+[A-Z])(?!\s*:)")
_GLUED = re.compile(r"(?i)\b(incorporated|established|founded|set up|formed)(in)(\d{4})")
_HISTORY = re.compile(r"^(?:originally\s+)?(?:incorporated|established|founded|set up|formed|promoted)\b[^,.;]*?\b(?:in|on)\s+\d{4}\s*(?:,|as\b[^,]*,|and\b)?\s*", re.I)
# fix20 (LIVE14A-003: Prism Johnson "...was incorporated in 1992 and is amongst the largest ..."): a founding clause after the company's name
# left off, so its sentence says what it is now
_HISTORY_MID = re.compile(r"\b(?:was|has been)\s+(?:originally\s+)?(?:incorporated|established|founded|set up|formed)\b[^,.;]*?\b(?:in|on)\s+"
                          r"(?:\w+\s+)?(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(?:19|20)\d\d\s*,?\s*and\s+(?=(?:is|are|has|have|operates|manufactures|makes|"
                          r"provides|offers|sells|produces)\b)", re.I)
# fix20 (LIVE14A-003: Shell "Measured by both its own emissions ..., Shell was the ninth-largest corporate producer of greenhouse gas emissions
# in the period 1988–2015", an encyclopedia's sentence): a ranking in the past tense, a sentence opening "Measured by" or one of a period of
# years is a third party's account, never the company's own words about its work
_THIRD_PARTY = re.compile(r"\b(?:was|were)\s+(?:the|one\s+of\s+the|among\s+the)\s+(?:[\w-]+\s+){0,2}?(?:[\w]+-)?(?:largest|biggest|smallest|"
                          r"top)\b|^measured\s+by\b|\bin\s+the\s+period\s+(?:19|20)\d\d", re.I)


# e79 (LIVE15A-005/020, after the 19 Nov re-checks: Kopin "The Kopin Corporation is a Westborough, Massachusetts-based electronics manufacturer,
# best known for its microdisplay devices", Leidos "Founded as Science Applications International Corporation (SAIC), Leidos merged with ...",
# Wipro "... and is one of India's Big Six IT services companies", Exxon "It is vertically integrated across the entire oil and gas industry",
# Canadian Natural "It is the largest independent producer of natural gas in Western Canada", Lightpath "Historically, we operated ...", Metalink
# "From that time until February 2010 ...", Intchains "WFOE acquired approximately 82.49% equity interest ...", Square Four "... formerly known
# as ..."): an account of a company by a third party (what it is best known for, a place-based label, a founding name, a ranking among peers,
# a sentence of "It is" ranking it or saying how it is organised) or of its history (what it did before, from a time until a year, a stake it
# bought, a former name) is no line of its own words about its work
_ACCOUNT = re.compile(r"\bbest[- ]known\s+(?:for|as)\b|\b(?:is|was)\s+an?\s+(?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)-based\b|^founded\s+as\b|"
                      r"\bBig\s+(?:Three|Four|Five|Six|Seven|Eight|Ten)\b|"
                      r"^it\s+is\s+(?:(?:the|one\s+of\s+the|among\s+the)\s+(?:[\w-]+\s+){0,3}?(?:largest|biggest|top)\b|(?:vertically|fully)\s+integrated\b)|"
                      r"^(?:historically|formerly|previously|in\s+the\s+past)\b|^from\s+that\s+time\b|"
                      r"\bacquired\s+(?:approximately\s+|about\s+|an?\s+)?\d[\d.]*\s?%\s+(?:of\s+the\s+)?(?:equity\s+)?(?:interest|stake)\b|"
                      r"\bformerly\s+known\s+as\b", re.I)


# e80 (LIVE16A-002, after e79: XOM "As the largest U.S.-based oil and gas company, ExxonMobil is the eighth-largest company by revenue in the
# U.S. and 13th-largest in the world", BP "It is one of the oil and gas "supermajors" and one of the world's largest companies ...", Imperial
# Oil "In Canada, it is a major producer of crude oil", Suncor "It specializes in ...", Wipro "Wipro's services include ...", CrowdStrike "It
# provides endpoint security ...", TotalEnergies "Its businesses cover ..."): the source is the encyclopedia's summary that the description
# reader adds after a thin annual-report opening (theme_routes.evidence_reader); its extract is now kept apart ("wiki") and its sentences are
# never quoted (encyclopedia_sentence). Records read before keep the extract run into their words, so its voice is known too: a company spoken
# of as "it"/"its" (a filing says "we" or names itself), its short name's possessive opening a list of what it offers, and a ranking among
# the world's or the country's companies; a filing's cross-reference "(as defined below)" quoted out of its filing is no line either
_VOICE = re.compile(r"^(?:in|across|throughout|within)\s+[A-Z][\w.&' -]{1,40},\s+(?:it|its)\s+\w+|^it\s+is\s+one\s+of\b|"
                    r"^its\s+(?:businesses|operations|activities)\s+(?:cover|span|include|range)\b|"
                    r"^[A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)?['’]s\s+(?:services|products|businesses|operations|offerings|activities|portfolio)\s+"
                    r"(?:include|includes|cover|covers|span|spans|range)\b|"
                    r"\bone\s+of\s+the\s+(?:world['’]s|country['’]s|nation['’]s|[\w-]+\s+\w+\s+\W?supermajors\W?)\b|\bsupermajors?\b|"
                    r"\b(?:\d+(?:st|nd|rd|th)|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)[- ]largest\b|^as\s+the\s+(?:largest|biggest)\b|"
                    r"\(as\s+defined\s+(?:below|above|herein)\)", re.I)
_ENCYC_SEEN: dict = {}          # normalised sentence -> True: the sentences of encyclopedia extracts read with a description (bounded)
_ENCYC_PRE: dict = {}           # its first ENCYC_PRE characters -> True (a quoted line cut short of the sentence's end)
ENCYC_SEEN_MAX = 20000
ENCYC_PRE = 60


def _norm_sentence(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def note_encyclopedia(extract: str) -> None:
    """e80: the sentences of an encyclopedia's extract kept with a company's description: never quoted as its own words."""
    for x in _sentences(" ".join(str(extract or "").split())):
        n = _norm_sentence(x)
        if len(n) >= 20:
            _ENCYC_SEEN[n] = True
            if len(n) >= ENCYC_PRE:
                _ENCYC_PRE[n[:ENCYC_PRE]] = True
    for d in (_ENCYC_SEEN, _ENCYC_PRE):
        while len(d) > ENCYC_SEEN_MAX:
            d.pop(next(iter(d)))


# e80: a US company's stored words are its annual report's (which speaks as "we", "the Company" or its own name) or the encyclopedia's; a
# sentence that speaks of the company as "it"/"its" is the encyclopedia's (an Indian profile's "It manufactures steel wheels" is its own)
_PRONOUN = re.compile(r"^(?:it|its)\s+(?!also\b)[a-z]+", re.I)


def note_us_voice(about: str) -> None:
    """e80: the sentences of a US company's stored words that speak of it as "it"/"its", noted as the encyclopedia's (note_encyclopedia)."""
    xs = [x for x in _sentences(" ".join(str(about or "").split())) if _PRONOUN.match(x)]
    if xs:
        note_encyclopedia(" ".join(x if x.endswith((".", ";", "!", "?")) else x + "." for x in xs))


def encyclopedia_sentence(t: str) -> bool:
    """e80: whether a line is (the start of) a sentence of an encyclopedia extract kept with a description, or speaks in its voice (_VOICE)."""
    if _VOICE.search(" ".join(str(t or "").split()).lstrip(" “\"'")):
        return True
    n = _norm_sentence(t)
    return len(n) >= 20 and (n in _ENCYC_SEEN or (len(n) >= ENCYC_PRE and n[:ENCYC_PRE] in _ENCYC_PRE))


# e81 (LIVE17A-002, after e80: the theme dive's "In its own words" quoted Qualcomm "The company develops and designs technologies for global
# communications and computing, including next-generation mobi" (cut mid-word), Astera Labs "Astera Labs, Inc., headquartered in San Jose,
# California, is a fabless manufacturing company", Cadence "Initially specialized in electronic design automation (EDA) software ..., the
# company currently makes ..." and Microsoft "The company became influential in the rise of personal computers ...", while the members table
# above it showed none of them): those US records were read before the encyclopedia's extract was kept apart, the extract run into the words
# (first, before e57, or after a thin annual-report opening), so no note of it exists. Its run is known by its opening: an encyclopedia's lead
# (_ENCYCLOPEDIA: "is an American multinational ...", a place-based label, "<Name>, headquartered in <Place>, is a ...") and every sentence
# after it up to the first in the filing's own voice ("We ...", "Our ..."); a fragment the store cut short (no sentence end) is no quote either
_LEAD_WHERE = re.compile(r"^[A-Z][^.;]{0,80}?,\s+(?:headquartered|based)\s+in\s+[^,;]{2,60}(?:,\s+[^,;]{2,40})?,\s+(?:is|was)\s+an?\b")
_FILER_VOICE = re.compile(r"^(?:we|our|us)\b|^item\s+\d|^(?:overview|general|business)\b", re.I)
_SENTENCE_START = re.compile(r"(?<=[a-z0-9,])\s+(?=(?:We|Our)\s)")         # a filing's "We ..." run on after a cut fragment ("... mobi We are")
_FILER_MARK = re.compile(r"\b(?:[Ww]e|[Oo]ur)\b|\((?:the\s+)?[\"“](?:Company|we)[\"”]")     # a filing's own voice anywhere in a sentence
CUT_NEAR = 600                  # characters: a description this long may end where the store cut it (theme_check.EVIDENCE_CHARS, 700)


def encyclopedia_lead(sentence: str) -> bool:
    """e81: whether a sentence opens an encyclopedia's account of a company (its lead: nationality or "multinational", a place-based label,
    "<Name>, headquartered in <Place>, is a ...")."""
    t = " ".join(str(sentence or "").split()).lstrip(" “\"'")
    return bool(_ENCYCLOPEDIA.search(_ABBR_DOT.sub(r"\1", t)) or _LEAD_WHERE.search(_ABBR_DOT.sub(r"\1", t))
                or re.search(r"\b(?:is|was)\s+an?\s+(?-i:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)-based\b", t))


def quotable(about, region: str = "") -> str:
    """e81: a company's stored words as a page may quote them (theme_data's dive, as the members table reads them): without the sentences of an
    encyclopedia's extract (noted ones, encyclopedia_sentence; for a US record, the run from an encyclopedia's lead to the first sentence in
    the filing's own voice) and without a last fragment the store cut short of a sentence's end. The text as it is when nothing is taken off;
    "" for none."""
    t = " ".join(str(about or "").split())
    if not t or t.startswith("From its own filings:"):
        return t
    parts = [y.strip() for x in _sentences(t) for y in _SENTENCE_START.split(x) if y.strip()]
    keep, run = [], False
    for x in parts:
        if region == "US" and encyclopedia_lead(x):
            run = True
        elif run and (_FILER_VOICE.match(x) or _FILER_MARK.search(x)):
            run = False
        if run or encyclopedia_sentence(x):
            continue
        keep.append(x)
    # cut by the store mid-sentence (or mid-word: a description is kept to its first EVIDENCE_CHARS characters): never quoted; a short
    # description that simply ends without a full stop keeps its line
    if keep and len(parts) > 1 and keep[-1] == parts[-1] and (region == "US" or len(t) >= CUT_NEAR) \
            and not keep[-1].rstrip(" ”\"')").endswith((".", "!", "?", ";", ":")):
        keep = keep[:-1]
    out = " ".join(keep)
    return t if out == t else out


def without_history(text: str) -> str:
    """fix20: a description's founding clause after the company's name left off ("X Limited was incorporated in 1992 and is ..." -> "X Limited
    is ...")."""
    return _HISTORY_MID.sub("", str(text or ""))
# a results or sales line, not what the company does: "reported total dispatches of 7,34,403 units in October 2026"
_PRESS = re.compile(r"\b(?:reported|announced|posted|recorded|registered|clocked)\b.{0,60}\d|\b\d[\d,.]*\s*(?:units|crore|lakh|million|billion)\b.{0,30}"
                    r"\b(?:in|for|during)\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|q[1-4]|fy)", re.I)
_DOES = re.compile(r"\b(?:manufactur|make|produc|suppl|provid|engag|offer|design|develop|sell|operat|build|distribut|deal|trad|serv|run|own|"
                   r"leader|maker|player|largest|company|business)", re.I)


def _sentences(t: str) -> list[str]:
    return [x.strip() for x in re.split(_NOT_END + r"(?<=[.;])\s+(?=[A-Z“\"(])", t) if x.strip()]


def one_line(about: str) -> str:
    """The first sentence of a company's own description that says what it does (its words): headings and markdown left off, words an
    extraction glued together parted ("Incorporatedin1994"), a founding-history opening and a results line (units sold in a month) skipped.
    A sentence too long for the line is cut at a word with an ellipsis, never mid-word. "" when there is no description."""
    t = _HEADING.sub(". ", _MARKUP.sub(" ", _GLUED.sub(r"\1 \2 \3", str(about or ""))))
    t = " ".join(re.sub(r"^[\s.]+|(?<=[.;])\s*\.\s", " ", t).split())
    if not t:
        return ""
    if t.startswith("From its own filings:"):           # the filings that back a company with no description: said as filings (own_filings)
        m = _FIRST.match(t)
        return (m.group(1) if m else t[:200]).rstrip(" .;")
    picks = []
    for x in _sentences(t):
        x = _HISTORY.sub("", x).strip(" ,;:-–—")
        if len(x) < 15 or _PRESS.search(x):
            continue
        picks.append(x)
    best = next((x for x in picks if _DOES.search(x)), picks[0] if picks else "")
    if not best:
        m = _FIRST.match(t)
        best = "" if _PRESS.search(t) else (m.group(1) if m else t)
    if not best:
        return ""
    m = _FIRST.match(best + " ")
    if m:
        return m.group(1).rstrip(" .;")
    if len(best) <= 240:
        return best.rstrip(" .;")
    cut = best[:220]
    return cut_end(cut[:cut.rfind(" ")]) + "…"


# LIVE6-007 (the live Cybersecurity page: "From its own filings: Annual report (20-F)", "Fortinet, Inc." alone, encyclopedia lead sentences
# such as "... is an American multinational corporation headquartered in Sunnyvale, California"): a line is shown as a company's own words
# only when it says what the company does
NO_WORDS = "No description in its own words yet"
_WORK = re.compile(r"\b(?:provid\w*|produc(?:es|ers?|ing|ts?|tion)|manufactur\w*|makes?|making|makers?|sells?|selling|suppl(?:y|ies|ying|iers?)|"
                   r"designs?|designing|develop(?:s|ing|ers?)|operat(?:es|ing|ors?)|offers?|offering|distribut\w*|retail\w*|services?|servic(?:es|ing)|"
                   r"foundr(?:y|ies)|licens\w*|leases?|leasing|lend(?:s|ing|ers?)|insur\w*|earns?|revenues?|customers?|clients?|subscri\w*|platforms?|"
                   r"stores?|brands?|engag(?:ed|es)|build(?:s|ing|ers?)|construct\w*|mines?|mining|miners?|refin\w*|generat(?:es|ing|ors?)|transmi\w*|"
                   r"explor(?:es|ing|ation)|invest(?:s|ing|ments?)|manag(?:es|ing)|deliver\w*|software|hardware|solutions?|products?|systems?|"
                   r"equipment|devices?|vehicles?|drugs?|medicines?|banking|bank|loans?|chemicals?|steel|cement|power|electricity|"
                   r"specializ\w*|specialis\w*|focus(?:es|ed) on|helps?|enables?|protect\w*|secur(?:es|ing)|"
                   # gl52 (R52: Visa, "facilitates digital payments", shown with no words of its own)
                   r"payments?|transactions?|process(?:es|ing)|facilitat\w*|"
                   # r62 (the live R60 Homebuilders deck: Toll Brothers' "We cater to luxury first-time, move-up ... buyers", the sentence
                   # that says its layer, read as no work, so a strategy sentence was printed for "Luxury and custom homebuilding")
                   r"cater(?:s|ing)? to)\b", re.I)
_FILING_TITLE = re.compile(r"^(?:annual|quarterly|current|interim|half[- ]yearly)\s+report\b|^(?:form\s+)?(?:10-[kq]|20-f|40-f|8-k|6-k|def\s*14a)\b|"
                           r"^(?:press release|investor presentation|board meeting|outcome of board meeting|shareholding pattern|financial results)\b", re.I)
_LEGAL_WORDS = re.compile(r"\b(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|nv|sa|ag|the|holdings?|group)\b\.?", re.I)


# LIVE7A-004 (the live Semiconductors page: TOYO Co.'s "own words" were Toyo Tire's encyclopedia article, Monolithic Power's "an American,
# publicly traded company headquartered in West Palm Beach", AMD's "We also offer ...", Dillard's "It is headquartered in Little Rock ..."):
# an encyclopedia's opening line (a nationality or "multinational" right after "is a", "commonly known as") is not the company's own words,
# nor a line that only adds to what an earlier one said ("also", "In addition") or only says where it is
_ENCYCLOPEDIA = re.compile(r"^[^.]{0,160}?\b(?:is|was)\s+(?:an?|the)\s+(?:[\w&'-]+,?\s+){0,3}?(?:American|British|English|Scottish|Japanese|Taiwanese|"
                           r"(?:South\s+)?Korean|Chinese|Indian|Israeli|Dutch|German|French|Swiss|Canadian|Irish|Swedish|Finnish|Norwegian|Danish|"
                           r"Italian|Spanish|Belgian|Australian|Singaporean|Brazilian|Mexican|Argentine|Bermudian|Luxembourgish|Greek|Cypriot|"
                           r"multinational|publicly[\s-]traded)\b|^[^.]{0,80}?,\s+(?:commonly|also|formerly|better)\s+known\s+as\b", re.I)
_ABBR_DOT = re.compile(r"\b(inc|corp|co|ltd|plc|l\.p|n\.v|s\.a|bhd|pty|ltda|st)\.", re.I)      # "Inc." doesn't end the opening clause
_ADDS = re.compile(r"^(?:in\s+addition\b|additionally\b|also\b|(?:we|it|they|the\s+company)\s+also\b)", re.I)
# r62 (LIVE10A-004, the live review of R61: quotes printed as a company's own words on the app, the CSV and the public blog: Ambuja "is among the
# leading cement companies in India", Shree "…is ** one of the lowest cost producers", Intel's "third-largest ... Fortune 500", ASML's "…industry
# and", Arteris "particularl”", TOYO Co. quoted with Toyo Tire's words): a line whose subject was cut off (it starts with an ellipsis or a bare
# verb), that carries markup, that ends on a joining word or with an unclosed quote, that ranks the company in a list as an encyclopedia does,
# or whose subject is another company that shares only its first word, is no line of its own words
# (r63e, the live R62 Homebuilders deck: Installed Building Products printed as "In the late 1990s, we began our acquisition strategy ...")
_CUT_LEAD = re.compile(r"^(?:…|\.\.\.|(?:is|was|are|were|has|have|had|which|and|but|or)\b|in the (?:(?:early|mid|late)[- ])?(?:19|20)\d0s\b|from (?:our|its) inception\b|"
                       r"created by\b|founded (?:in|by)\b)", re.I)
_CUT_END = re.compile(r"\b(?:and|or|of|the|a|an|to|in|with|for|by|on|at|from|as|its|their)\W*$", re.I)
_RANKED = re.compile(r"\b(?:fortune|forbes|global)\s+(?:500|1000|2000|global 500)\b|\b(?:(?:second|third|fourth|fifth|sixth|\d+(?:st|nd|rd|th))[- ]largest|largest)\b"
                     r"[^.]{0,60}\bby (?:revenue|sales|market cap\w*)\b[^.]{0,40}\b(?:19|20)\d\d\b", re.I)
_LEGAL_NAME = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "llc", "lp", "holdings", "holding", "group",
               "the", "and", "of", "sa", "ag", "nv", "se", "ab", "asa", "spa", "bhd", "pty", "industries", "international", "intl"}


def other_subject(text: str, name: str) -> bool:
    """r62 (LIVE10A-004): whether a description's subject, the capitalised name that opens it, is another company than `name` that shares only
    its first word ("Toyo Tire Corporation is ..." for "TOYO Co., Ltd."): its second word is a distinctive word the company's name lacks."""
    m = re.match(r"\s*((?:[A-Z][\w&'.-]*\s+){1,5}?)(?:is|was|are|has|operates|manufactures|makes|provides|\()", str(text or ""))
    if not m or not name:
        return False
    subj = re.findall(r"[A-Za-z][\w'-]*", m.group(1))
    own = [w.lower() for w in re.findall(r"[A-Za-z][\w'-]*", str(name))]
    if len(subj) < 2 or not own or subj[0].lower() != own[0]:
        return False
    second = subj[1].lower().strip(".")
    if second in _LEGAL_NAME or len(second) < 3:
        return False
    return not any(w.startswith(second[:4]) or second.startswith(w[:4]) for w in own[1:] if len(w) >= 3)
_WHERE = re.compile(r"^(?:it|we|the\s+company)\s+(?:is|are)\s+(?:headquartered|based|located|domiciled|incorporated)\b", re.I)


# r66e (LIVE12A-001: Osi Systems "As of June 2010, the company employs approximately 3,180 personnel…", Penguin Solutions "The company rebranded
# to SMART Global Holdings (SGH) and held an initial public offering in 2017…", quoted as their own words about their work): a line dated years
# back ("As of June 2010"), a head count, or a line of the company's history (a rebranding, a renaming, its listing) says nothing of its work
_DATED = re.compile(r"^as of (?:[a-z]+ )?(?:\d{1,2},? )?((?:19|20)\d\d)\b", re.I)
_HISTORY_LINE = re.compile(r"\bemploy(?:s|ed|ing)?\b[^.;]{0,40}?\b\d[\d,.]*\s+(?:personnel|employees|people|staff|workers|associates)\b|"
                           r"\b(?:rebranded|renamed|changed its (?:corporate )?name)\b|\b(?:held|completed|made|launched) (?:an|its) initial public offering\b|"
                           r"\bwent public\b", re.I)


def history_line(text: str, today_year: int | None = None) -> bool:
    """r66e: whether a line is a dated fact of years back, a head count or the company's history, not its work."""
    from datetime import date
    t = " ".join(str(text or "").split())
    m = _DATED.match(t)
    if m and int(m.group(1)) < (today_year or date.today().year) - 2:
        return True
    return bool(_HISTORY_LINE.search(t))


# r66e (LIVE12A-001: TOYO Co., Ltd, a solar cell maker, "Description-verified" on Toyo Tire's encyclopedia article, "…distributes tires and
# automotive components through fourteen sales com…"; Inno Holdings' stored words opening on "INNOvative Retail BV, is an upmarket Belgian
# department store chain", another company's article, before its own annual report): a description that opens on another company, one whose
# name shares the company's first word but has a word of its own the company's name lacks, is not the company's words until a sentence names
# the company itself or speaks as it ("we", "our"); "the company" and "it" still speak of the other one
_NAME_LINK = {"&", "and", "of", "de", "la", "du", "von"}
_NAME_LEGAL = _LEGAL_NAME | {"bv", "gmbh", "sas", "kk", "oyj", "spa", "srl", "ltda", "pte", "pvt", "private", "public", "the", "llp", "sarl", "inc.", "co.", "corp."}


def _subject(sentence: str) -> list[str]:
    """The capitalised name a sentence opens with, as lowercased words ("Toyo Tire Corporation , commonly known…" -> toyo, tire, corporation)."""
    out = []
    toks = str(sentence or "").split()
    if toks and toks[0] in ("The", "THE"):
        toks = toks[1:]
    for tok in toks[:8]:
        w = tok.strip(",.;:“”\"'’")
        if not w:
            break
        if w.lower() in _NAME_LINK and out:
            continue
        if not w[0].isupper() or tok.startswith("("):
            break
        out.append(w.lower().replace(".", ""))
        if tok.endswith((",", ";", ":")) and not re.match(r"(?i)^(?:inc|ltd|llc|corp|co|plc|n\.?v|s\.?a|ag)\b", (toks[toks.index(tok) + 1] if toks.index(tok) + 1 < len(toks) else "")):
            break
    return out


def _co_name_words(name: str) -> list[str]:
    if listing_line(name) or unit_line(name):          # a depositary receipt's or a unit trust's line: its issuer's name
        name = issuer_name(name)
    return [w for w in (x.lower() for x in re.findall(r"[A-Za-z][\w'-]*", str(name or ""))) if w not in _NAME_LEGAL]


def _co_same_word(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def fuller_name(subj: list[str], own: list[str]) -> bool:
    """r68e (R68, the owner's review of the live R66 Building materials deck: Jindal Steel Limited, description-verified as a steel mill in
    R65, "no description of its own is stored yet" in R66: its words open on "Jindal Steel & Power Limited", its name before 2025, read as
    another company's): a subject that says every word of a name of two words or more (a word, or the initials of the subject's words that
    follow: "SEZ" of "Special Economic Zone") is the company under its fuller or earlier name. A name of one word (TOYO) never is."""
    words = [w for w in subj if w not in _NAME_LEGAL and w not in _NAME_LINK]
    if len(own) < 2:
        return False

    def said(o):
        if any(_co_same_word(w, o) for w in words):
            return True
        return len(o) >= 2 and any("".join(w[0] for w in words[i:i + len(o)]) == o for i in range(len(words)))
    return all(said(o) for o in own)


def names_other(sentence: str, name: str) -> bool:
    """r66e: whether a sentence opens on another company than `name` that shares its first word (Toyo Tire for TOYO Co., Ltd). r68e: never
    the company under its fuller or earlier name (fuller_name: "Jindal Steel & Power Limited" for Jindal Steel Limited)."""
    subj, own = _subject(sentence), _co_name_words(name)
    if len(subj) < 2 or not own or not _co_same_word(subj[0], own[0]) or fuller_name(subj, own):
        return False
    flat = "".join(own)
    for w in subj[1:]:
        if w in _NAME_LEGAL or len(w) < 3 or w in _NAME_LINK:
            continue
        if not any(_co_same_word(w, o) or w[:4] == o[:4] for o in own) and w not in flat:
            return True
    return False


def names_self(sentence: str, name: str) -> bool:
    """r66e: whether a sentence names the company itself (its name's first word opening it, not another company's) or speaks as it."""
    t = str(sentence or "").lstrip(" “\"'(")
    if re.match(r"(?:we|our|us)\b", t, re.I):
        return True
    subj, own = _subject(t), _co_name_words(name)
    return bool(subj and own and _co_same_word(subj[0], own[0]) and not names_other(t, name))


def own_part(about, name: str = "") -> str:
    """r66e: a stored description without the opening sentences that speak of another company (names_other), up to the first that names the
    company or speaks as it; "" when none does. The description as it is when it doesn't open on another company (or no name is known)."""
    t = " ".join(str(about or "").split())
    if not t or not name or t.startswith("From its own filings:"):
        return t
    sents = re.split(_NOT_END + r"(?<=[.;!?])\s+(?=[A-Z“\"(])", t)
    if not sents:
        return t
    # e79 (LIVE15A-020: TOYO Co., Ltd, a solar cell maker, quoted in the dive as "The company owns and operates eight factories ... and
    # distributes tires and automotive components through fourteen sales companies": Toyo Tire's article run on after its own lines): a run of
    # sentences that opens on another company, anywhere in the words, is left out up to the next sentence that names the company or speaks as
    # it; "the company" and "it" within the run still speak of the other one
    keep, other = [], False
    for x in sents:
        if names_other(x, name):
            other = True
        elif other and names_self(x, name):
            other = False
        if not other:
            keep.append(x)
    return " ".join(keep).strip() if len(keep) < len(sents) else t


_DEFINES = re.compile(r"\s*\((?=[^()]*(?:\btogether with\b|\bcollectively\b|“(?:we|our|us|Company|the Company)[,”]|\bthe “Company))[^()]*\)")


def own_words(text, name: str = "") -> str:
    """A company's line as its own words on a page, a CSV or a slide, or "" when it isn't one (LIVE6-007): the titles of its filings (the
    "From its own filings:" lines stand in for a missing description in the checks, never as one), its name alone, or a sentence that says
    where it is and what it is called but not what it does (says no work: provides, makes, sells, operates; its software, its customers);
    LIVE7A-004: an encyclopedia's opening line, a line that only adds to an earlier one, or one that only says where the company is."""
    t = " ".join(str(text or "").split()).strip(" “”\"'")
    # r581 (the live R58 Cybersecurity deck: SailPoint's line "(together with its consolidated subsidiaries, as appropriate, “SailPoint,” the
    # “Company,” “our,” or “we”)"): the bracket a filing defines its own name in says nothing of the work, and is left out
    t = _DEFINES.sub("", t).strip()
    t = t[:1].upper() + t[1:] if t[:1].islower() and str(text or "").lstrip(" “”\"'").startswith("(") else t
    # fix20 (LIVE14A-003): a heading run into the text ends it there; a founding clause after the name is left off; a third party's account
    # (a past ranking, "Measured by", a period of years) is no line of its own words
    hd = _HEADING_RUN_IN.search(t)
    if hd and hd.start() > 0:
        t = t[:hd.start()].rstrip(" ,;:")
    t = without_history(t)
    if _THIRD_PARTY.search(t) or _ACCOUNT.search(t) or encyclopedia_sentence(t):
        return ""
    if not t or t.startswith("From its own filings:") or _FILING_TITLE.match(t) or _ENCYCLOPEDIA.search(_ABBR_DOT.sub(r"\1", t)) or _ADDS.match(t) or _WHERE.match(t):
        return ""
    # r62 (LIVE10A-004): markup taken off; a cut subject or end, an unclosed quote, a ranked list or another company's subject is no line
    t = " ".join(t.replace("**", " ").split())
    if _CUT_LEAD.match(t) or _CUT_END.search(t) or str(text).count("“") != str(text).count("”") or _RANKED.search(t) or other_subject(t, name) \
            or history_line(t):
        return ""
    words = lambda x: [w for w in re.findall(r"[a-z0-9]+", _LEGAL_WORDS.sub(" ", x.lower()))]        # noqa: E731
    if name and not [w for w in words(t) if w not in set(words(name))]:
        return ""
    return t if _WORK.search(t) else ""


# v55 (R55, the owner's review of the live R54 Payments deck: "Adyen Nv-Unspon ADR" listed as a company whose own description identifies another
# business, though no description of it was ever read: the encyclopedia was asked for "Adyen Nv-Unspon ADR", which names no company, so the
# issuer's own description, an end-to-end payments platform's, never reached the check): a listing line names its issuer only once the words
# that describe the line are taken off (a depositary receipt, sponsored or not, a share class, a registry or an ordinary-share line)
_LISTING_LINE = re.compile(r"(?:[\s,-]+(?:(?:un)?spon(?:sored|s)?\.?|american depositary (?:shares?|receipts?)|global depositary (?:shares?|receipts?)|"
                           r"depositary (?:shares?|receipts?)|adrs?|adss?|gdrs?|ny reg(?:istry)?(?: shs| shares)?|ord(?:inary)?(?: shs| shares)?|"
                           r"shs|level (?:i{1,3}|[123])|(?:cl|class) [a-c]|each repr\w*.*|repr?\.? \d.*))+\s*$", re.I)
_UNSPONSORED = re.compile(r"\bun-?spon(?:sored|s)?\b", re.I)
_DEPOSITARY = re.compile(r"\b(?:adrs?|adss?|gdrs?|depositary (?:shares?|receipts?))\b", re.I)
_LEGAL_TAIL = re.compile(r"[,.]?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|n\.?v|s\.?a|s\.?e|ag|a[ /]?s|ab|asa|oyj|spa|"
                         r"holdings?)\.?$", re.I)


# e57 (RC7, the live R56 Real estate deck: "Brookfield India Real Estate Trust - REIT", "Property Share Investment Trust- Propshare Titania"
# looked up as listed, no description found): a unit trust's listing words after its name, the "- REIT"/"- InvIT" mark or an SM REIT's scheme
_UNIT_TAIL = re.compile(r"\s*-\s*(?:reit|invit)\s*$|(?<=\btrust)\s*-\s*\S.*$|\s+(?:reit|invit)\s*$", re.I)


def unit_line(name: str) -> bool:
    """e57: whether a name is a REIT's or InvIT's listing line, with listing words after the trust's name (issuer_name takes them off)."""
    return bool(_UNIT_TAIL.search(" ".join(str(name or "").split())))


def issuer_name(name: str) -> str:
    """v55: the issuer a listing line stands for, with the line's own words and the legal form taken off ("Adyen Nv-Unspon ADR" -> "Adyen",
    "Qnity Electronics, Inc." -> "Qnity Electronics"); the name itself when nothing is left. e57: a unit trust's "- REIT"/"- InvIT" mark or
    an SM REIT's scheme after the trust's name too ("Nexus Select Trust - REIT" -> "Nexus Select Trust")."""
    t = " ".join(str(name or "").split())
    t = _UNIT_TAIL.sub("", t).strip(" ,.-") or t
    out = _LISTING_LINE.sub("", re.sub(r"\s*\((?:[^()]*\b(?:repr|ord|adrs?|adss?|shares?)\b[^()]*)\)\s*$", "", t, flags=re.I)).strip(" ,.-")
    for _ in range(2):
        out = _LEGAL_TAIL.sub("", out).strip(" ,.-")
    return out or t


def listing_line(name: str) -> str:
    """v55: what kind of listing line a name is, said as a reason ("listed in the US as an unsponsored depositary receipt of Adyen"), or ""
    for an ordinary share line."""
    t = str(name or "")
    if not _DEPOSITARY.search(t):
        return ""
    kind = "an unsponsored depositary receipt" if _UNSPONSORED.search(t) else "a depositary receipt"
    return f"listed as {kind} of {issuer_name(t)}"


OWN_LINE_MAX = 300              # r64e (LIVE11A-003): a sentence of a company's own words quoted whole up to this many characters


def own_line(about, name: str = "") -> str:
    """gl52 (R52, the rotating review of Release 51: Visa, Mastercard, Fortinet and Trade Desk shown with "No description in its own words
    yet", their stored words an encyclopedia's opening line): the first sentence of a description that is the company's own words about its
    work (own_words), else one_line's sentence as before."""
    first = one_line(about)
    if not first or own_words(first, name) or str(about or "").startswith("From its own filings:"):
        return first
    # r64e (LIVE11A-003: Micron's "…deliver the speed, efficiency, and scal", its sentence cut at 240 characters mid-word): a sentence
    # is quoted whole up to OWN_LINE_MAX characters; a longer one ends at its last clause within them (a comma or semicolon), else at a word, with an ellipsis; one the
    # stored description's own cut ends loses its cut word (whole_words)
    flat = " ".join(str(about or "").split())
    sents = _sentences(flat)
    for i, x in enumerate(sents):
        x = _HISTORY.sub("", x).strip(" ,;:-–—")
        if len(x) >= 15 and not _PRESS.search(x) and own_words(x, name):
            m = _FIRST.match(x + " ")
            one = (m.group(1) if m else x).rstrip(" .;")
            if i == len(sents) - 1 and not re.search(r"[.!?;”\")]$", flat):
                one = whole_words(one, flat) or one
            if len(one) <= OWN_LINE_MAX:
                return one
            at = max(one.rfind(", ", 0, OWN_LINE_MAX), one.rfind("; ", 0, OWN_LINE_MAX))
            return cut_end(one[:at] if at > 120 else one[:one.rfind(" ", 0, 238)]) + "…"
    return first


def has_own_line(about, name: str = "") -> bool:
    """Whether a stored description has a sentence in the company's own words about its work (own_line), not only an encyclopedia's."""
    return bool(own_words(own_line(about, name), name))


def whole_words(what, about) -> str:
    """A company's line with a word cut by the end of its stored description taken off and an ellipsis in its place (LIVE7A-004: ADI's "a
    broad portfolio of solutio", eBay's "via retail sal": a description is kept to its first EVIDENCE_CHARS characters, so its last word can
    be part of one). Only a line that runs to the very end of a description that doesn't end a sentence is touched."""
    w = " ".join(str(what or "").split())
    a = " ".join(str(about or "").split())
    if not w or not a or " " not in w or a.rstrip(" ”\"'").endswith((".", "!", "?", ")", ";")):
        return w
    norm = lambda x: re.sub(r"\W+", " ", x).strip().lower()        # noqa: E731
    wn, an = norm(w), norm(a)
    if not wn or not an.endswith(wn[-40:]):
        return w
    return w[:w.rfind(" ")].rstrip(" ,;:-–—") + "…"


def described(m: dict, about_of, region: str = "") -> dict:
    """The map with each official layer's company carrying `what`: the first sentence of its own description, from `about_of(symbol)`
    (the description or None; it never reads more than the caller allows). A company with none keeps "", which the page shows as not yet
    confirmed from its own description."""
    out = dict(m)
    vc = []
    for v in m.get("value_chain") or []:
        if v.get("official") or any(c.get("placed") for c in v.get("companies") or []):
            cos = []
            for c in v.get("companies") or []:
                if v.get("official") or c.get("placed"):          # a company placed after the map shows its own words too (R21)
                    about = about_of(c["ticker"])
                    # (e82, LIVE18A-003: of the words a page may quote, never an encyclopedia's sentence: quotable)
                    q_ = quotable(about, region) if about else ""
                    c = {**c, "what": own_line(q_, c.get("name") or "") if q_ else ""}       # gl52: its own words first
                cos.append(c)
            v = {**v, "companies": cos}
        vc.append(v)
    out["value_chain"] = vc
    return out


# ---------- US companies with no industry on file ----------
# A US company whose page isn't built has no SIC code in the index (967 of 7,021 on 4 Nov). Each theme check reads a few of their SEC
# records (the submissions JSON the company pages read) and keeps the code, so they join a theme by industry; no job of its own.
SIC_KEY = "theme:sic:US"
SIC_DAYS = 30                   # a company the SEC gave no code for is asked again after this long
SIC_PER_RUN = 40                # records read in one theme check, at most
SIC_BUDGET = 20.0               # ...and seconds spent on them


def with_sic(rows: list[dict], stored: dict) -> list[dict]:
    """The index rows with the industry kept from the SEC's record filled in where the index has none."""
    paths = (stored or {}).get("paths") or {}
    out = []
    for r in rows or []:
        p = paths.get(r.get("symbol")) if not r.get("industry") else None
        out.append({**r, "sector": r.get("sector") or p[0], "industry": p[-1]} if p else r)
    return out


def unclassified(rows: list[dict]) -> int:
    return sum(1 for r in rows or [] if r.get("symbol") and not r.get("industry"))


def fill_sic(rows: list[dict], stored: dict, read, now=None, limit: int = SIC_PER_RUN, budget: float = SIC_BUDGET) -> tuple[dict, int]:
    """(the kept codes with up to `limit` more read, how many were read). `read(symbol)` -> the SIC path ([division, industry]), [] when
    the SEC has none, or raises when it can't answer now (tried again next time). Largest first, then A to Z; a company tried within
    SIC_DAYS with no code is skipped."""
    import time as _t
    now = now or datetime.now(timezone.utc)
    stored = {"paths": dict((stored or {}).get("paths") or {}), "tried": dict((stored or {}).get("tried") or {})}
    cut = (now.date().toordinal() - SIC_DAYS)
    todo = []
    for r in sorted(rows or [], key=lambda r: (-(r.get("market_cap") or 0), str(r.get("symbol")))):
        s = r.get("symbol")
        if not s or r.get("industry") or s in stored["paths"]:
            continue
        t = stored["tried"].get(s)
        if t and datetime.fromisoformat(t).date().toordinal() > cut:
            continue
        todo.append(s)
    started, n = _t.monotonic(), 0
    for s in todo[:limit]:
        if _t.monotonic() - started > budget:
            break
        try:
            path = read(s)
        except Exception as e:
            print("theme base: SEC record not read:", s, type(e).__name__, str(e)[:80])
            continue
        n += 1
        if path:
            stored["paths"][s] = list(path)[:2]
            stored["tried"].pop(s, None)
        else:
            stored["tried"][s] = now.date().isoformat()
    return stored, n


# r60 (R60, the owner's outside review of the live R59 decks, P0 "verify company activity against layer semantics": Dish TV India, "in the
# business of providing Direct to Home television and Teleport services", sent from "Cable and satellite distribution" to "Other" because
# its words hold no literal word of the layer's name): a company's own words are matched to a layer by the layer's concept, not only by the
# literal words of its name. A concept is a reviewed group of the words a business of one kind is described by. A layer has it when its
# name says a word that gives it, or the first sentence of the map's own description of the layer does (a narrower set: a word as common as
# "distribution" in a description gives none). Each row: (name words that give it, description words that give it, the words of a
# company's own words that say it). Kinds of business only: never a company's or a theme's name.
LAYER_CONCEPTS = (
    # satellite television distribution: direct-to-home (DTH) and teleport services
    (r"\bsatellite\b", r"\bsatellite\b", r"\bdirect[- ]to[- ]home\b|\bdth\b|\bteleports?\b"),
    # reinsurance
    (r"\bre-?insur", r"\bre-?insur", r"\bre-?insur\w*"),
    # insurance distribution: broking, aggregation and marketplaces for policies
    (r"\bdistribution\b|\baggregat\w*|\bbrok(?:ing|ers?|erage)\b", r"\baggregat\w*|\binsurance brok\w*",
     r"\b(?:re)?insurance brok(?:ing|ers?|erage)\b|\bbrok(?:ing|ers?) (?:of|for) insurance\b|\b(?:web|insurance|online) aggregators?\b|"
     r"\binsurance (?:market ?places?|distribution|distributors?)\b|\bmarket ?places? for (?:insurance|policies)\b|"
     r"\bdistribut\w*\b[^.;]{0,30}?\b(?:insurance|financial products|policies)\b|\b(?:online|digital) (?:platforms?|market ?places?) for (?:insurance|policies)\b"),
    # analog and power semiconductors
    (r"\banalog(?:ue)?\b", r"\banalog(?:ue)?\b",
     r"\banalog(?:ue)?\b|\bpower (?:management )?(?:ics?|integrated circuits?|semiconductors?|chips?)\b|\bmixed[- ]signal\b|\bembedded processing\b"),
    # r62 (the live R60 US Telecom deck's "Components and chips", Qorvo "an American semiconductor company", read as no word of it): chips,
    # semiconductors and integrated circuits (never a layer of chip-making equipment, tools or materials, its own row)
    (r"^(?!.*\b(?:equipment|tools?|machines?|materials?)\b).*\b(?:chips?|semiconductors?)\b", r"^(?!.*\b(?:equipment|tools?|machines?|materials?)\b).*\bchips?\b",
     r"\bsemiconductors?\b|\bintegrated circuits?\b|\bchipsets?\b|\bsystems?[- ]on[- ]chips?\b|\bchips?\b"),
    # memory chips
    (r"\bmemory\b", r"\bmemory chips?\b", r"\bmemory\b|\bdram\b|\bnand\b|\bflash (?:memory|storage)\b"),
    # chip-making equipment: a layer of semiconductor, chip or wafer equipment, tools or machines
    (r"\b(?:semiconductor|chip|wafer)s?\b.*\b(?:equipment|tools?|machines?)\b|\b(?:equipment|tools?|machines?)\b.*\b(?:semiconductor|chip|wafer)s?\b",
     r"\bwafer fab\w*|\bchip[- ]?making\b|\blithograph\w*",
     r"\b(?:photo)?lithograph\w*|\bwafer (?:fab(?:rication)? )?(?:equipment|processing|inspection)\b|\bchip[- ]?making (?:equipment|machines?|tools?|systems?)\b|"
     r"\bsemiconductor (?:manufacturing |capital |fabrication |production )?(?:equipment|machines?|machinery|tools?)\b|"
     r"\b(?:deposition|etch(?:ing)?) (?:and|equipment|systems?|tools?)\b|\bprocess control\b|\bmetrology\b"),
    # oilfield services: drilling, well and seismic services
    (r"\boil ?field\b|\bdrilling\b", r"\boil ?field\b|\bdrilling\b",
     r"\boil ?field services?\b|\b(?:offshore|onshore|contract) drilling\b|\bdrilling (?:rigs?|services?|contractors?|units?)\b|\bjack-?up rigs?\b|"
     r"\bwell (?:services?|intervention|completion)\b|\bseismic (?:data|surveys?|services?|acquisition)\b"),
    # security software: cybersecurity, firewalls, threat protection
    (r"\bsecurity\b", r"\bcyber[- ]?security\b",
     r"\bcyber[- ]?security\b|\bfirewalls?\b|\bendpoint (?:security|protection)\b|\bthreat (?:detection|intelligence|protection|prevention)\b|\bnetwork security\b"),
    # resale: trading in goods others make, wholesale, reselling
    (r"\bresale\b|\bresellers?\b", r"\bresale\b|\breselling\b",
     r"\btrading (?:in|of)\b|\btraders? (?:of|in)\b|\bcommodity trading\b|\bwholesal\w*|\bre-?sell\w*|\bresale\b|\brecommerce\b|"
     # r66e (the live R65 Consumer retail deck: "Resale, rental and small digital commerce" over Inno Holdings, "the business of recycled
     # consumer electronic devices", read as no word of it): goods sold again, pre-owned, second-hand, refurbished or recycled consumer goods
     r"\b(?:pre-?owned|second[- ]?hand|refurbished|recycled|used) (?:consumer )?(?:electronic devices|electronics|devices|smartphones?|phones|goods|"
     r"products|cars|vehicles|apparel|clothing|fashion|luxury goods)\b"),
    # special alloys: superalloys, special purpose steels, special metals
    (r"\balloys?\b", r"\bsuperalloys?\b|\bspecial (?:purpose )?(?:steels?|metals)\b",
     r"\b(?:super)?alloys?\b|\bspecial (?:purpose )?steels?\b|\bspecial metals\b|\btitanium\b"),
    # contract manufacturing: electronics manufacturing services (EMS, ESDM), box build, build to print, outsourced assembly and test
    (r"\bcontract (?:manufactur|mak)\w*|\bmanufacturing services\b", r"\bcontract manufactur\w*|\bmanufacturing services\b",
     r"\bcontract manufactur\w*|\belectronics? manufacturing services\b|\b(?:electronics? )?system design and manufacturing\b|\besdm\b|"
     r"\bems\b|\bbox[- ]build\b|\bbuild[- ]to[- ]print\b|\boutsourced (?:manufactur|assembl)\w*|\bmanufacturing services\b|\bosat\b|"
     r"\bassembly,? (?:and )?test(?:ing)?\b"),
    # value retail formats: variety, dollar, discount and off-price stores
    (r"\bvalue (?:retail|stores?|formats?|chains?)\w*|\bdollar\b|\bdiscount\w*|\boff-price\b", r"\bvariety (?:items|stores?|goods)\b|\bdiscount (?:stores?|chains?)\b|\boff-price\b",
     r"\bvariety (?:store chains?|stores?|retail\w*|chains?)\b|\bdollar stores?\b|\bdiscount (?:stores?|retail\w*|chains?|variety)\b|\bvalue retail\w*|\boff-price\b"),
    # r65e (the live R64 Railroads and trucking deck: "Asset-light brokers and agents" over C.H. Robinson, "one of the largest global logistics
    # providers in the world", read as no word of it): freight brokerage, arranging others' carriers' capacity for shippers: a logistics
    # provider, third-party logistics, freight brokerage, arranging shipments (a layer of asset-light brokers or agents, or of freight brokers)
    (r"\basset[- ]light\b.*\b(?:brok\w*|agents?)\b|\b(?:freight|truck\w*|logistics|transportation|cargo)\b.*\bbrok\w*|\bbrok\w*\b.*\b(?:freight|truck\w*|logistics|transportation|cargo)\b",
     r"\bmatch\w* shippers\b|\bfreight brok\w*",
     r"\bfreight brok\w*|\b(?:transportation|truckload|logistics) brok\w*|\b(?:third[- ]party )?logistics providers?\b|\bthird[- ]party logistics\b|"
     r"\b3pl\b|\barrang\w* (?:for )?(?:individual |the )?(?:shipments?|transportation|freight)\b|\bnon-?asset\b|\basset[- ]light\b"),
    # r65e (the R65 replay of the US Aerospace and defense input: "Ordnance and accessories", a layer of that official industry, over Sturm
    # Ruger, "the design, manufacture, and sale of firearms", and Smith & Wesson, "manufacturers and designers of firearms", read as no word of
    # it): ordnance is firearms and their ammunition
    (r"\bordnance\b", r"\bordnance\b", r"\bordnance\b|\bfirearms?\b|\bammunition\b|\bhandguns?\b|\brifles?\b|\bpistols?\b|\bshotguns?\b"),
)


# r68e (R68, the owner's review of the live R66 REITs deck: Camden Property Trust, "175 multifamily properties comprised of 59,921 apartment
# homes", in "Manufactured housing and RV communities" (and in R65 in "Healthcare property owners"): the words a layer's name and a company
# share ("communities", "property") made it fit, and the layer of apartment owners had been renamed for its three manufactured-housing
# members): a property owner's layer fits a company by the kind of property each names. A layer's name that states a property owner's
# business (PROPERTY_OWNER: landlords, property, storage, communities...) names its property types (by_name); a company's own words name
# theirs (says). A company that names property types none of which its layer's name names is no member of that layer by its words, and one
# naming one of them is, whatever other words they share. Kinds of property only: never a company's or a theme's name. Each row: (type,
# the words of a layer's name that name it, the words of a company's own words that say it)
PROPERTY_TYPES = (
    ("multifamily", r"\bresidential\b|\bapartments?\b|\bmulti-?family\b|\bstudent housing\b",
     r"\bmulti-?family\b|\bapartments?\b|\bstudent housing\b"),
    ("single-family rental", r"\bresidential\b|\bsingle-?family\b|\bhomes? (?:for )?rent|\brental homes?\b",
     r"\bsingle-?family (?:rental )?(?:homes?|houses|properties|residences)\b|\bhomes for (?:rent|lease)\b|\brental homes\b|\bbuild-to-rent\b"),
    ("manufactured housing and RV", r"\bresidential\b|\bmanufactured\b|\b(?:rv|recreational vehicles?)\b|\bmarinas?\b",
     r"\bmanufactured (?:hous\w*|homes?)\b|\brecreational vehicles?\b|\b(?:rv|mh) (?:communities|resorts|parks|sites)\b|\bmarinas?\b"),
    ("office", r"\boffices?\b", r"\boffice (?:properties|property|buildings?|space|assets|portfolio|campus\w*|towers?|parks?|markets?)\b|"
     r"\bclass a office\b|\boffice and (?:retail|industrial|life science)\b"),
    ("healthcare", r"\bhealth ?care\b|\bmedical\b|\bseniors?\b|\bhospitals?\b|\bnursing\b",
     r"\bhealth ?care (?:properties|facilities|real estate|related facilities|reits?)\b|\bseniors? (?:housing|living)\b|"
     r"\bskilled nursing\b|\bmedical office\b|\boutpatient medical\b|\bhospitals?\b|\bpost-acute\b|\bassisted living\b|\bmemory care\b"),
    ("industrial and logistics", r"\bindustrial\b|\blogistics\b|\bwarehous\w*",
     r"\bindustrial (?:properties|property|real estate|buildings?|facilities|assets|portfolio|and logistics)\b|\bwarehouses?\b|"
     r"\blogistics (?:facilities|properties|real estate|space)\b|\bdistribution (?:centers|centres|facilities)\b"),
    ("cold storage", r"\bcold[- ]storage\b|\btemperature[- ]controlled\b", r"\bcold[- ]storage\b|\btemperature[- ]controlled\b"),
    ("self-storage", r"\bself[- ]storage\b", r"\bself[- ]storage\b|(?<!cold )(?<!cold-)\bstorage (?:facilities|units|properties|stores)\b"),
    ("data centres", r"\bdata cent(?:er|re)s?\b", r"\bdata cent(?:er|re)s?\b|\bcolocation\b|\binterconnection\b"),
    ("communications towers", r"\btowers?\b", r"\b(?:cell|wireless|communications?|telecom\w*) (?:towers?|sites|infrastructure)\b|(?<!office )\btowers?\b"),
    ("retail", r"\bretail\b|\bshopping\b|\bmalls?\b|\boutlets?\b",
     r"\bshopping (?:centers?|centres?|malls?)\b|\bmalls?\b|\bretail (?:properties|property|real estate|centers?|centres?|space|assets|"
     r"portfolio|and mixed-use)\b|\bstrip centers?\b|\boutlet centers?\b|\bgrocery-anchored\b|\bopen-air\b"),
    ("net lease", r"\bnet[- ]lease\w*", r"\bnet[- ]lease\w*|\btriple[- ]net\b|\bsingle-tenant\b"),
    ("lodging", r"\bhotels?\b|\blodging\b|\bleisure\b|\bresorts?\b|\bhospitality\b",
     r"\bhotels?\b|\blodging\b|\bresorts?\b|\bhospitality properties\b"),
)
PROPERTY_OWNER = re.compile(r"\blandlords?\b|\bpropert(?:y|ies)\b|\breal estate\b|\breits?\b|\bowners?\b|\bcommunities\b|\bstorage\b|"
                            r"\btowers?\b|\bnet[- ]lease\b", re.I)
_PROPERTY_SPEAKER = re.compile(r"\breal estate\b|\breits?\b|\bpropert(?:y|ies)\b|\blandlords?\b|\bleas(?:e|es|ed|ing)\b|\brent(?:s|al|ed)?\b|"
                               r"\bcommunit(?:y|ies)\b|\bowns?\b", re.I)


def layer_property_types(name: str) -> set[str]:
    """r68e: the property types a property owner's layer's name names (PROPERTY_TYPES), a half's "(larger)" aside; none for a name that
    states no property owner's business (PROPERTY_OWNER: "Office products" or "Hotel operators" judge nothing)."""
    low = _HALF_RX.sub("", str(name or "")).lower()
    if not PROPERTY_OWNER.search(low):
        return set()
    return {t for t, by_name, _ in PROPERTY_TYPES if re.search(by_name, low)}


# a list of kinds before what is owned ("office, retail, and multifamily assets", "medical office buildings"): each kind read as a layer's
# name word would be
_PROPERTY_LIST = re.compile(r"\b((?:[a-z][a-z-]*,\s*){0,5}(?:[a-z][a-z-]*,?\s+(?:and|or|&)\s+)?[a-z][a-z-]*)\s+(?:properties|property|assets|"
                            r"buildings?|real estate|facilities|portfolios?|communities|space)\b", re.I)


def _property_hits(text: str) -> list[tuple[int, str]]:
    """r68e: (where, type) of each property type a text names, its own phrases (PROPERTY_TYPES) and the kinds of a list before what is
    owned (_PROPERTY_LIST); the first place each type is named."""
    t = " ".join(str(text or "").split())
    hits = {}
    for ty, by_name, says in PROPERTY_TYPES:
        m = re.search(says, t, re.I)
        if m:
            hits[ty] = m.start()
    for m in _PROPERTY_LIST.finditer(t):
        kinds = m.group(1).lower()
        for ty, by_name, _ in PROPERTY_TYPES:
            k = re.search(by_name, kinds)
            # ("residential", a name's word for every kind of housing, names none of them in a company's own list)
            if k and k.group(0) != "residential" and (ty not in hits or m.start() + k.start() < hits[ty]):
                hits[ty] = m.start() + k.start()
    return sorted((at, ty) for ty, at in hits.items())


def company_property_types(text: str) -> set[str]:
    """r68e: the property types a property owner's own words name (PROPERTY_TYPES, a list of kinds before what is owned too); none for
    words that speak of no property they own, lease or rent (_PROPERTY_SPEAKER)."""
    t = " ".join(str(text or "").split())
    if not t or not _PROPERTY_SPEAKER.search(t):
        return set()
    return {ty for _, ty in _property_hits(t)}


def property_fit(name: str, text: str) -> bool | None:
    """r68e: whether a company's own words name a property type its property owner's layer's name names (True), only types it doesn't
    (False), or nothing to judge by: the name states no property type, or the words name none (None)."""
    lt = layer_property_types(name)
    if not lt:
        return None
    ct = company_property_types(text)
    if not ct:
        return None
    return bool(lt & ct)


def layer_concepts(layer: str, description: str = "", by_property: bool = True) -> list[str]:
    """r60: the patterns of the words that say a layer's concept (LAYER_CONCEPTS), by its name (a half's "(larger)" aside) or the first
    sentence of its own description."""
    name = _HALF_RX.sub("", str(layer or "")).lower()
    first = re.split(r"(?<=[.!?])\s", " ".join(str(description or "").split()), maxsplit=1)[0].lower()
    pts = layer_property_types(name) if by_property else set()          # r68e: a property owner's layer's concept is the kinds of property its name names
    return [says for by_name, by_desc, says in LAYER_CONCEPTS if re.search(by_name, name) or (first and re.search(by_desc, first))] \
        + [says for t, _, says in PROPERTY_TYPES if t in pts]


def concept_said(layer: str, text: str, description: str = "", by_property: bool = True) -> re.Match | None:
    """r60: the first words of a company's own words that say a concept of a layer (layer_concepts); None when none do."""
    t = str(text or "")
    if not t.strip():
        return None
    hits = [m for rx in layer_concepts(layer, description, by_property) for m in [re.search(rx, t, re.I)] if m]
    return min(hits, key=lambda m: (m.start(), m.group(0))) if hits else None


_GATE_GENERIC = {"and", "or", "of", "the", "for", "in", "to", "with", "by", "on", "from", "other", "others", "own", "their", "they", "them",
                 "company", "companies", "firms", "players", "business", "businesses", "group", "groups", "service", "services", "product",
                 "products", "goods", "consumer", "consumers", "customer", "customers", "client", "clients", "makers", "maker", "producers",
                 "producer", "suppliers", "supplier", "providers", "provider", "sellers", "seller", "owners", "owner", "operators",
                 "partners", "specialty", "speciality", "diversified", "integrated", "sized", "small", "smaller", "large", "larger", "mid",
                 "scale", "wide", "broad", "general", "focused", "led", "based", "commercial", "listed", "segment", "segments", "related",
                 "allied", "plus", "global", "domestic", "new", "solutions", "systems"}
_GATE_SUFFIXES = ("ations", "ation", "ings", "ing", "ers", "er", "ies", "es", "s", "ed", "al")


def _gate_stem(w: str) -> str:
    for suf in _GATE_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[:-len(suf)]
            break
    return w[:5]


def gate_says(name: str, text: str) -> bool | None:
    """r62: whether a company's words, official industry and name say a word of a layer's name or its concept, as the release gate reads them
    (release_gate.shares); None when the name has no word that says a business."""
    nw = {_gate_stem(w) for w in re.findall(r"[a-z0-9]+", str(name or "").lower().replace("&", " and "))
          if len(w) > 2 and not w.isdigit() and w not in _GATE_GENERIC}
    if not nw:
        return None
    tw = {_gate_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower().replace("&", " and ")) if len(w) > 2}
    return any(a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))) for a in nw for b in tw) \
        or bool(concept_said(name, text))


def concepts_said(layer: str, text: str, description: str = "") -> int:
    """r60: how many concepts of a layer a company's own words say."""
    t = str(text or "")
    return sum(1 for rx in layer_concepts(layer, description) if t.strip() and re.search(rx, t, re.I))


# r581 (the live R58 decks' "layer words": Insurance's "Distribution and aggregation" over PB Fintech's "popularly known as Policy Bazar is
# India's largest online platform for insurance", Pharma's "Biologics and novel drug developers" over Biocon's "engaged in the business of
# manufacture of biotechnology products"): a company's line in its layer says the words that place it there when its own words have them
LINE_PLAIN = NAME_GENERIC | {"manufacturer", "manufacturers", "manufacturing", "platform", "platforms", "software", "technology", "technologies",
                             "stage", "portfolio", "portfolios", "leading", "mixed", "various", "regional", "national", "tier", "high", "value",
                             "added", "basic", "performance", "premium", "quality", "operator", "solution", "system", "pan", "india"}
LINE_MAX = 110                  # the characters of a line a deck's table shows (deck.whole_clause)
_LINE_HEADING = re.compile(r"^(?:Business (?:Model|Overview|Profile|Segments?|Divisions?)\b\s*:?|[A-Z][A-Za-z&/ -]{2,40}\s*:|[a-z]\)|\d+[.)])\s*")
_GLUED_HEADING = re.compile(r"\s+(?=Business (?:Model|Overview|Profile|Segments?|Divisions?)\b)")      # a description's heading run into the text


def layer_words(layer: str) -> set[str]:
    """The words of a layer's name that say a kind of business (plural "s" off), the generic ones left out."""
    out = set()
    for w in re.findall(r"[a-z]+", _HALF_RX.sub("", str(layer or "")).lower().replace("-", " ")):
        if len(w) >= 3 and w not in LINE_PLAIN:
            out.add(w[:-1] if w.endswith("s") and len(w) > 4 and not w.endswith("ss") else w)
    return out - LINE_PLAIN


_LEGAL_FORM = re.compile(r"[,.]?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|l\.p|n\.?v|s\.?a|ag|se|holdings?|"
                         r"group|trust|reit)\.?$", re.I)


def name_aside(text: str, name: str) -> str:
    """e78: a company's words with its own name, as a phrase, left out (its full name, then the name without its legal form: "American Homes
    4 Rent" out of "American Homes 4 Rent ("AMH") is ..."), the rest of its words as they are."""
    t, nm = str(text or ""), " ".join(str(name or "").split())
    forms = []
    while nm and nm not in forms:
        forms.append(nm)
        nm = _LEGAL_FORM.sub("", nm).strip(" ,.")
    for f in sorted((f for f in forms if len(f) >= 3), key=len, reverse=True):
        t = re.sub(r"(?<![A-Za-z0-9])" + re.escape(f) + r"(?![A-Za-z0-9])", " ", t, flags=re.I)
    return t


def _line_says(text: str, w: str) -> re.Match | None:
    return re.search(r"\b" + re.escape(w[:max(5, len(w) - 2)] if len(w) > 6 else w), text.lower())


def layer_line(line: str, about, name: str, layer: str, description: str = "") -> str:
    """A company's line for its layer: `line` when it says a word of the layer's name (layer_words; the company's own name aside), else the
    first sentence of its own words about its work (own_words) that does, up to the clause that says it, with a heading ("Business
    Segments: a) Biosimilars:") and asides in brackets left out, the word within the LINE_MAX characters a table shows; else `line`."""
    ws = layer_words(layer)
    # r60: the words that say the layer's concept place it as its name's words do (layer_concepts: "Direct to Home" of "satellite"), so
    # the line printed is the sentence that supports the placement
    cx = layer_concepts(layer, description)
    text = " ".join(str(about or "").split())
    if not (ws or cx) or not text or text.startswith("From its own filings:"):
        return line
    named = {w.lower() for w in re.findall(r"[A-Za-z]+", str(name or ""))}
    bare = lambda t: " ".join(w for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", t) if w.lower() not in named)      # noqa: E731
    # e78 (the owner's review of the live R76 REITs deck: American Homes 4 Rent, "leasing and managing single-family homes as rental
    # properties", in "Other" as its words "hold no line" of "Residential landlords": every word of its name taken out of its sentence left
    # "single-family as rental properties", which no kind of property says): a concept's words are read with the company's name itself
    # left out (name_aside), never each word its name happens to share with them
    unnamed = lambda t: name_aside(t, name)          # noqa: E731
    if line and (any(_line_says(bare(line), w) for w in ws) or any(re.search(rx, unnamed(line), re.I) for rx in cx)):
        return line
    for sent in [p for x in _sentences(text) for p in _GLUED_HEADING.split(x)]:
        sent = re.sub(r"\s*\([^()]*\)", "", sent).strip()
        for _ in range(4):
            sent = _LINE_HEADING.sub("", sent, count=1).strip()
        sent = re.sub(r"\s+([,;:])", r"\1", sent).rstrip(" .;:")
        upto = ""
        for clause in re.split(r"(?<=[,;])\s+", sent):
            upto = f"{upto} {clause}".strip()
            # r59: the word said first in the clause, never whichever the set of the name's words gives first (the line a deck printed
            # for a company changed from one run to the next with the order of a set)
            hit = min((m for m in [*(_line_says(bare(clause), w) for w in ws), *(re.search(rx, unnamed(clause), re.I) for rx in cx)] if m),
                      key=lambda m: (m.start(), m.group(0)), default=None)
            if hit is None:
                continue
            one = upto.rstrip(" ,;:")
            # r64e (LIVE11A-003: Credo's line "We design", of "We design, market and sell both product, software and IP solutions";
            # Monolithic Power's "... a fabless global company that provides high-performance", its sentence going on ", semiconductor-
            # based power electronics solutions"): the whole sentence when it fits, or when what follows the clause is one more phrase
            # with no clause of its own (the noun the clause's words describe); a line is never a clause of under four words
            rest_ = sent[len(upto):].strip(" ,;:")
            # (only where the clause itself is a line of its own words: the sentence never lets in a clause the rules leave out)
            if one != sent and own_words(one, name) and own_words(sent, name) and (len(sent) <= LINE_MAX or (len(rest_) <= 60 and not re.search(r"[,;:]|\s(?:and|or|which|while|including)\s", rest_))):
                return sent[:1].upper() + sent[1:]
            if len(one.split()) < 4 and one != sent:
                continue
            at = len(upto) - len(clause) + clause.lower().find(hit.group(0))
            if len(one) <= LINE_MAX or at + len(hit.group(0)) <= LINE_MAX - 10:
                if own_words(one, name):
                    return one[:1].upper() + one[1:]
            break
    return line
