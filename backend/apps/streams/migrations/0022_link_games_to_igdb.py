"""Mark the real games that Twitch left without an IGDB id.

categorize_games takes a Twitch category with no igdb_id for a non-game, and
approve_streams deletes a stream that played only non-games. Twitch leaves some real
games unlinked, so their streams were being deleted: Counter-Strike and Dota 2 are the
biggest.

The rule stays the same - a category listed on IGDB is a game - and these ids come from
looking the titles up on IGDB by hand. The next enrich_igdb_games run fills in their
genres. Touhou Project, OOC, The Playable Anime and Christmas Shopping Simulator aren't
listed on IGDB, so they stay non-games.

Where a category covers a pair, like Pokemon X/Y, the id is the pair's first game.
"""

from django.db import migrations

# Twitch's category id: IGDB's game id.
IGDB_IDS = {
    32399: 242408,  # Counter-Strike = Counter-Strike 2
    29595: 2963,  # Dota 2
    512821: 137688,  # Words On Stream = Words on Stream
    494099: 27979,  # Kingdom Hearts HD 1.5 + 2.5 ReMIX = Kingdom Hearts HD 1.5 + 2.5 Remix
    1584836809: 328373,  # Schedule I
    13332: 1559,  # Pokémon FireRed/LeafGreen = Pokémon FireRed Version
    75467: 3070,  # Euro Truck Simulator 2
    493174: 11529,  # Jackbox Party Packs = The Jackbox Party Pack
    417969: 7348,  # Halo: The Master Chief Collection
    13389: 327,  # Age of Empires II = Age of Empires II: The Age of Kings
    12924: 132,  # Warcraft III = Warcraft III: Reign of Chaos
    490422: 239,  # StarCraft II = StarCraft II: Wings of Liberty
    1568081763: 140839,  # Mass Effect Legendary Edition
    670867987: 191931,  # Pokémon Scarlet/Violet = Pokémon Scarlet
    23857: 1556,  # Pokémon HeartGold/SoulSilver = Pokémon HeartGold Version
    497451: 37382,  # Pokémon Sword/Shield = Pokémon Sword
    499551: 296792,  # World of Tanks Console = World of Tanks: Modern Armor
    33734: 8284,  # Pokémon Black/White Version 2 = Pokémon Black Version 2
    1584745140: 144051,  # Pokémon Brilliant Diamond/Shining Pearl = Pokémon Brilliant Diamond
    19009: 37,  # Dead Space (2008) = Dead Space
    518847: 135915,  # Overcooked! All You Can Eat
    497334: 36792,  # Pokémon Ultra Sun/Ultra Moon = Pokémon Ultra Sun
    27602: 1521,  # Pokémon Black/White = Pokémon Black Version
    460327: 6897,  # Pokémon Omega Ruby/Alpha Sapphire = Pokémon Omega Ruby
    103828: 2286,  # Pokémon X/Y = Pokémon X
    498160: 209297,  # The Joy of Creation
    922931567: 25877,  # Pokémon: Let's Go, Pikachu!/Eevee! = Pokémon: Let's Go, Pikachu!
    3623: 1561,  # Pokémon Red/Blue = Pokémon Red Version
    508391: 109096,  # Krunker
    964600247: 1289,  # Ratchet & Clank (2002) = Ratchet & Clank
    10710: 241,  # Counter-Strike 1.6 = Counter-Strike
    1446426412: 138227,  # Super Mario 3D World + Bowser's Fury
    517497: 133887,  # Tony Hawk's Pro Skater 1+2
    11849: 2655,  # Animal Crossing
    9287: 1557,  # Pokémon Ruby/Sapphire = Pokémon Ruby Version
    995720898: 549,  # God Of War (2005) = God of War
    12826: 2319,  # Pokémon Mystery Dungeon: Blue/Red Rescue Team = Pokémon Mystery Dungeon: Red Rescue Team
    494155: 24920,  # Call of Duty: Modern Warfare Remastered
    506327: 23719,  # Neverwinter Nights: Enhanced Edition
    1391915212: 146075,  # The Great Ace Attorney Chronicles
    2993: 1560,  # Pokémon: Diamond/Pearl = Pokémon Diamond Version
    503977: 222654,  # Devil May Cry 1 - HD = Devil May Cry
    491599: 18100,  # Pokémon Sun/Moon = Pokémon Sun
    1748876120: 83829,  # Lifeline (2003) = Lifeline
    19147: 1067,  # Super Mario Bros. 2
    496490: 26167,  # Bulletstorm: Full Clip Edition
    488492: 36240,  # Icewind Dale: Enhanced Edition
    517072: 137700,  # Dead by Daylight Mobile
    114674: 3185,  # Madden NFL 25 (2013) = Madden NFL 25
    66450: 13180,  # Serious Sam HD: The First Encounter
    504440: 27988,  # Planescape: Torment: Enhanced Edition = Planescape: Torment - Enhanced Edition
    491354: 137711,  # Evil Bane
    10502: 4499,  # Dr. Robotnik's Mean Bean Machine
    19413: 2321,  # Pokémon Mystery Dungeon: Explorers of Darkness/Time = Pokémon Mystery Dungeon: Explorers of Time
    914991832: 241125,  # Five Nights at Freddy's Plus
    13642: 3727,  # Kirby's Avalanche
    1694: 17249,  # Ninja Gaiden III: The Ancient Ship of Doom
    1356039710: 31699,  # DEADLOCK (2016) = Deadlock
    1908684124: 166073,  # DeadLock (2021) = DeadLock
    2112842660: 392380,  # MyWhoosh
    6003: 11452,  # Revelations: Persona
    491334: 91272,  # Kartrider = Crazyracing Kartrider
    66451: 13181,  # Serious Sam HD: The Second Encounter
    736129280: 138796,  # Chronos: Before the Ashes
    518709: 135770,  # Devolverland Expo
    3108: 1760,  # Mega Man Battle Network 4 = Mega Man Battle Network 4: Blue Moon
    417793: 22344,  # Rise of Nations: Extended Edition
    10501: 121504,  # Need for Speed: Most Wanted 5-1-0
    94090: 64147,  # CSPromod
    1338005147: 131931,  # Dead Space Mobile = Dead Space
    413014954: 146473,  # Essays on Empathy
    416185: 137585,  # Mega Man Battle Network Chrono X
    65634: 137518,  # Mstar
    65640: 137023,  # My Little Pony: Fighting is Magic
    516562: 97402,  # Overpass (2020) = Overpass
    21889: 238937,  # Rhapsody II: Ballad of the Little Princess
    21888: 238548,  # Rhapsody III: Memories of Marl Kingdom
    500079: 26129,  # The Incredible Adventures of Van Helsing: Final Cut
    517315: 134365,  # Warface: Breakout
}


def mark_as_games(apps, schema_editor):
    Game = apps.get_model("streams", "Game")
    games = list(Game.objects.filter(host_game_id__in=IGDB_IDS, category="isnongame"))
    for game in games:
        game.category = "isgame"
        game.igdb_game_id = IGDB_IDS[game.host_game_id]
    Game.objects.bulk_update(games, ["category", "igdb_game_id"])


def mark_as_non_games(apps, schema_editor):
    Game = apps.get_model("streams", "Game")
    Game.objects.filter(host_game_id__in=IGDB_IDS).update(category="isnongame", igdb_game_id=0)


class Migration(migrations.Migration):

    dependencies = [
        ("streams", "0021_stream_live_idx_fillfactor"),
    ]

    operations = [
        migrations.RunPython(mark_as_games, mark_as_non_games),
    ]
