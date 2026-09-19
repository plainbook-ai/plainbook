{
 "cells": [
  {
   "cell_type": "code",
   "execution_count": null,
   "id": "424061a7",
   "metadata": {
    "code_timestamp": "2026-03-03T09:45:52.506304",
    "explanation": "Read in a Pandas dataframe the results of international football matches, available from \"https://raw.githubusercontent.com/martj42/international_results/master/results.csv\"",
    "explanation_timestamp": "2026-03-03T09:45:50.955220",
    "name": "load_football_data",
    "variables": {
     "df": {
      "columns": [
       {
        "dtype": "str",
        "name": "date"
       },
       {
        "dtype": "str",
        "name": "home_team"
       },
       {
        "dtype": "str",
        "name": "away_team"
       },
       {
        "dtype": "int64",
        "name": "home_score"
       },
       {
        "dtype": "int64",
        "name": "away_score"
       },
       {
        "dtype": "str",
        "name": "tournament"
       },
       {
        "dtype": "str",
        "name": "city"
       },
       {
        "dtype": "str",
        "name": "country"
       },
       {
        "dtype": "bool",
        "name": "neutral"
       }
      ],
      "shape": [
       49071,
       9
      ],
      "type": "DataFrame"
     }
    }
   },
   "outputs": [
    {
     "data": {
      "text/html": [
       "<div>\n",
       "<style scoped>\n",
       "    .dataframe tbody tr th:only-of-type {\n",
       "        vertical-align: middle;\n",
       "    }\n",
       "\n",
       "    .dataframe tbody tr th {\n",
       "        vertical-align: top;\n",
       "    }\n",
       "\n",
       "    .dataframe thead th {\n",
       "        text-align: right;\n",
       "    }\n",
       "</style>\n",
       "<table border=\"1\" class=\"dataframe\">\n",
       "  <thead>\n",
       "    <tr style=\"text-align: right;\">\n",
       "      <th></th>\n",
       "      <th>date</th>\n",
       "      <th>home_team</th>\n",
       "      <th>away_team</th>\n",
       "      <th>home_score</th>\n",
       "      <th>away_score</th>\n",
       "      <th>tournament</th>\n",
       "      <th>city</th>\n",
       "      <th>country</th>\n",
       "      <th>neutral</th>\n",
       "    </tr>\n",
       "  </thead>\n",
       "  <tbody>\n",
       "    <tr>\n",
       "      <th>0</th>\n",
       "      <td>1872-11-30</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>England</td>\n",
       "      <td>0</td>\n",
       "      <td>0</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>Glasgow</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>1</th>\n",
       "      <td>1873-03-08</td>\n",
       "      <td>England</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>4</td>\n",
       "      <td>2</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>London</td>\n",
       "      <td>England</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>2</th>\n",
       "      <td>1874-03-07</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>England</td>\n",
       "      <td>2</td>\n",
       "      <td>1</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>Glasgow</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>3</th>\n",
       "      <td>1875-03-06</td>\n",
       "      <td>England</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>2</td>\n",
       "      <td>2</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>London</td>\n",
       "      <td>England</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>4</th>\n",
       "      <td>1876-03-04</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>England</td>\n",
       "      <td>3</td>\n",
       "      <td>0</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>Glasgow</td>\n",
       "      <td>Scotland</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>...</th>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>49066</th>\n",
       "      <td>2026-01-18</td>\n",
       "      <td>Bolivia</td>\n",
       "      <td>Panama</td>\n",
       "      <td>1</td>\n",
       "      <td>1</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>Tarija</td>\n",
       "      <td>Bolivia</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>49067</th>\n",
       "      <td>2026-01-18</td>\n",
       "      <td>Grenada</td>\n",
       "      <td>Jamaica</td>\n",
       "      <td>0</td>\n",
       "      <td>1</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>St. George's</td>\n",
       "      <td>Grenada</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>49068</th>\n",
       "      <td>2026-01-22</td>\n",
       "      <td>Panama</td>\n",
       "      <td>Mexico</td>\n",
       "      <td>0</td>\n",
       "      <td>1</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>Panama City</td>\n",
       "      <td>Panama</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>49069</th>\n",
       "      <td>2026-01-25</td>\n",
       "      <td>Bolivia</td>\n",
       "      <td>Mexico</td>\n",
       "      <td>0</td>\n",
       "      <td>1</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>Santa Cruz</td>\n",
       "      <td>Bolivia</td>\n",
       "      <td>False</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>49070</th>\n",
       "      <td>2026-01-26</td>\n",
       "      <td>Uzbekistan</td>\n",
       "      <td>China PR</td>\n",
       "      <td>2</td>\n",
       "      <td>2</td>\n",
       "      <td>Friendly</td>\n",
       "      <td>Dubai</td>\n",
       "      <td>United Arab Emirates</td>\n",
       "      <td>True</td>\n",
       "    </tr>\n",
       "  </tbody>\n",
       "</table>\n",
       "<p>49071 rows × 9 columns</p>\n",
       "</div>"
      ],
      "text/plain": [
       "             date   home_team  ...               country  neutral\n",
       "0      1872-11-30    Scotland  ...              Scotland    False\n",
       "1      1873-03-08     England  ...               England    False\n",
       "2      1874-03-07    Scotland  ...              Scotland    False\n",
       "3      1875-03-06     England  ...               England    False\n",
       "4      1876-03-04    Scotland  ...              Scotland    False\n",
       "...           ...         ...  ...                   ...      ...\n",
       "49066  2026-01-18     Bolivia  ...               Bolivia    False\n",
       "49067  2026-01-18     Grenada  ...               Grenada    False\n",
       "49068  2026-01-22      Panama  ...                Panama    False\n",
       "49069  2026-01-25     Bolivia  ...               Bolivia    False\n",
       "49070  2026-01-26  Uzbekistan  ...  United Arab Emirates     True\n",
       "\n",
       "[49071 rows x 9 columns]"
      ]
     },
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "import pandas as pd\n",
    "\n",
    "df = pd.read_csv(\"https://raw.githubusercontent.com/martj42/international_results/master/results.csv\")\n",
    "df"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "id": "d09e8ca7",
   "metadata": {
    "code_timestamp": "2026-03-03T09:49:58.027910",
    "explanation": "List the 20 countries that have played most often (in columns home_team or away_team), along with the number of matches they have done. ",
    "explanation_timestamp": "2026-03-03T09:49:55.400320",
    "name": "count_team_appearances",
    "variables": {
     "all_matches": {
      "dtype": "float64",
      "len": 333,
      "type": "Series"
     },
     "away_matches": {
      "dtype": "int64",
      "len": 318,
      "type": "Series"
     },
     "df": {
      "columns": [
       {
        "dtype": "str",
        "name": "date"
       },
       {
        "dtype": "str",
        "name": "home_team"
       },
       {
        "dtype": "str",
        "name": "away_team"
       },
       {
        "dtype": "int64",
        "name": "home_score"
       },
       {
        "dtype": "int64",
        "name": "away_score"
       },
       {
        "dtype": "str",
        "name": "tournament"
       },
       {
        "dtype": "str",
        "name": "city"
       },
       {
        "dtype": "str",
        "name": "country"
       },
       {
        "dtype": "bool",
        "name": "neutral"
       }
      ],
      "shape": [
       49071,
       9
      ],
      "type": "DataFrame"
     },
     "home_matches": {
      "dtype": "int64",
      "len": 325,
      "type": "Series"
     },
     "result_df": {
      "columns": [
       {
        "dtype": "str",
        "name": "Country"
       },
       {
        "dtype": "int64",
        "name": "Number of Matches"
       }
      ],
      "shape": [
       20,
       2
      ],
      "type": "DataFrame"
     },
     "top_20": {
      "dtype": "float64",
      "len": 20,
      "type": "Series"
     }
    }
   },
   "outputs": [
    {
     "data": {
      "text/html": [
       "<div>\n",
       "<style scoped>\n",
       "    .dataframe tbody tr th:only-of-type {\n",
       "        vertical-align: middle;\n",
       "    }\n",
       "\n",
       "    .dataframe tbody tr th {\n",
       "        vertical-align: top;\n",
       "    }\n",
       "\n",
       "    .dataframe thead th {\n",
       "        text-align: right;\n",
       "    }\n",
       "</style>\n",
       "<table border=\"1\" class=\"dataframe\">\n",
       "  <thead>\n",
       "    <tr style=\"text-align: right;\">\n",
       "      <th></th>\n",
       "      <th>Country</th>\n",
       "      <th>Number of Matches</th>\n",
       "    </tr>\n",
       "  </thead>\n",
       "  <tbody>\n",
       "    <tr>\n",
       "      <th>0</th>\n",
       "      <td>Sweden</td>\n",
       "      <td>1097</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>1</th>\n",
       "      <td>England</td>\n",
       "      <td>1086</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>2</th>\n",
       "      <td>Argentina</td>\n",
       "      <td>1062</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>3</th>\n",
       "      <td>Brazil</td>\n",
       "      <td>1055</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>4</th>\n",
       "      <td>Germany</td>\n",
       "      <td>1027</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>5</th>\n",
       "      <td>South Korea</td>\n",
       "      <td>1003</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>6</th>\n",
       "      <td>Hungary</td>\n",
       "      <td>1002</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>7</th>\n",
       "      <td>Mexico</td>\n",
       "      <td>997</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>8</th>\n",
       "      <td>Uruguay</td>\n",
       "      <td>966</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>9</th>\n",
       "      <td>France</td>\n",
       "      <td>931</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>10</th>\n",
       "      <td>Italy</td>\n",
       "      <td>889</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>11</th>\n",
       "      <td>Poland</td>\n",
       "      <td>888</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>12</th>\n",
       "      <td>Switzerland</td>\n",
       "      <td>880</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>13</th>\n",
       "      <td>Netherlands</td>\n",
       "      <td>875</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>14</th>\n",
       "      <td>Denmark</td>\n",
       "      <td>870</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>15</th>\n",
       "      <td>Norway</td>\n",
       "      <td>868</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>16</th>\n",
       "      <td>Thailand</td>\n",
       "      <td>863</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>17</th>\n",
       "      <td>Austria</td>\n",
       "      <td>857</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>18</th>\n",
       "      <td>Belgium</td>\n",
       "      <td>849</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>19</th>\n",
       "      <td>Scotland</td>\n",
       "      <td>847</td>\n",
       "    </tr>\n",
       "  </tbody>\n",
       "</table>\n",
       "</div>"
      ],
      "text/plain": [
       "        Country  Number of Matches\n",
       "0        Sweden               1097\n",
       "1       England               1086\n",
       "2     Argentina               1062\n",
       "3        Brazil               1055\n",
       "4       Germany               1027\n",
       "5   South Korea               1003\n",
       "6       Hungary               1002\n",
       "7        Mexico                997\n",
       "8       Uruguay                966\n",
       "9        France                931\n",
       "10        Italy                889\n",
       "11       Poland                888\n",
       "12  Switzerland                880\n",
       "13  Netherlands                875\n",
       "14      Denmark                870\n",
       "15       Norway                868\n",
       "16     Thailand                863\n",
       "17      Austria                857\n",
       "18      Belgium                849\n",
       "19     Scotland                847"
      ]
     },
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "# Combine home_team and away_team to get all matches for each country\n",
    "home_matches = df['home_team'].value_counts()\n",
    "away_matches = df['away_team'].value_counts()\n",
    "\n",
    "# Sum the matches for each country\n",
    "all_matches = home_matches.add(away_matches, fill_value=0).sort_values(ascending=False)\n",
    "\n",
    "# Get the top 20 countries\n",
    "top_20 = all_matches.head(20)\n",
    "\n",
    "# Create a dataframe for better display\n",
    "result_df = pd.DataFrame({\n",
    "    'Country': top_20.index,\n",
    "    'Number of Matches': top_20.values.astype(int)\n",
    "}).reset_index(drop=True)\n",
    "\n",
    "result_df"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "id": "baf38363",
   "metadata": {
    "code_timestamp": "2026-03-03T09:54:44.381756",
    "explanation": "Create a \"win balance\" dataset, with 5 columns: Country, Number of Matches (as above), Wins Home, Wins Guest, Ties. \n* If home_score > away_score, the match is counted in the Wins Home for the home team. \n* If away_score > home_score, the match is counted in the Wins Away for the away team. \n* A match is counted as a tie if home_score = away_score. \n",
    "explanation_timestamp": "2026-03-03T09:54:41.949557",
    "name": "create_win_dataset",
    "variables": {
     "all_matches": {
      "dtype": "float64",
      "len": 333,
      "type": "Series"
     },
     "away_matches": {
      "dtype": "int64",
      "len": 318,
      "type": "Series"
     },
     "away_score": {
      "type": "int"
     },
     "away_team": {
      "type": "str"
     },
     "countries_list": {
      "len": 20,
      "type": "list"
     },
     "country": {
      "type": "str"
     },
     "country_stats": {
      "len": 333,
      "type": "defaultdict"
     },
     "df": {
      "columns": [
       {
        "dtype": "str",
        "name": "date"
       },
       {
        "dtype": "str",
        "name": "home_team"
       },
       {
        "dtype": "str",
        "name": "away_team"
       },
       {
        "dtype": "int64",
        "name": "home_score"
       },
       {
        "dtype": "int64",
        "name": "away_score"
       },
       {
        "dtype": "str",
        "name": "tournament"
       },
       {
        "dtype": "str",
        "name": "city"
       },
       {
        "dtype": "str",
        "name": "country"
       },
       {
        "dtype": "bool",
        "name": "neutral"
       }
      ],
      "shape": [
       49071,
       9
      ],
      "type": "DataFrame"
     },
     "home_matches": {
      "dtype": "int64",
      "len": 325,
      "type": "Series"
     },
     "home_score": {
      "type": "int"
     },
     "home_team": {
      "type": "str"
     },
     "idx": {
      "type": "int"
     },
     "matches_list": {
      "len": 20,
      "type": "list"
     },
     "result_df": {
      "columns": [
       {
        "dtype": "str",
        "name": "Country"
       },
       {
        "dtype": "int64",
        "name": "Number of Matches"
       }
      ],
      "shape": [
       20,
       2
      ],
      "type": "DataFrame"
     },
     "row": {
      "dtype": "object",
      "len": 9,
      "type": "Series"
     },
     "ties_list": {
      "len": 20,
      "type": "list"
     },
     "top_20": {
      "dtype": "float64",
      "len": 20,
      "type": "Series"
     },
     "win_balance_df": {
      "columns": [
       {
        "dtype": "str",
        "name": "Country"
       },
       {
        "dtype": "int64",
        "name": "Number of Matches"
       },
       {
        "dtype": "int64",
        "name": "Wins Home"
       },
       {
        "dtype": "int64",
        "name": "Wins Guest"
       },
       {
        "dtype": "int64",
        "name": "Ties"
       }
      ],
      "shape": [
       20,
       5
      ],
      "type": "DataFrame"
     },
     "wins_away_list": {
      "len": 20,
      "type": "list"
     },
     "wins_home_list": {
      "len": 20,
      "type": "list"
     }
    }
   },
   "outputs": [
    {
     "data": {
      "text/html": [
       "<div>\n",
       "<style scoped>\n",
       "    .dataframe tbody tr th:only-of-type {\n",
       "        vertical-align: middle;\n",
       "    }\n",
       "\n",
       "    .dataframe tbody tr th {\n",
       "        vertical-align: top;\n",
       "    }\n",
       "\n",
       "    .dataframe thead th {\n",
       "        text-align: right;\n",
       "    }\n",
       "</style>\n",
       "<table border=\"1\" class=\"dataframe\">\n",
       "  <thead>\n",
       "    <tr style=\"text-align: right;\">\n",
       "      <th></th>\n",
       "      <th>Country</th>\n",
       "      <th>Number of Matches</th>\n",
       "      <th>Wins Home</th>\n",
       "      <th>Wins Guest</th>\n",
       "      <th>Ties</th>\n",
       "    </tr>\n",
       "  </thead>\n",
       "  <tbody>\n",
       "    <tr>\n",
       "      <th>0</th>\n",
       "      <td>Sweden</td>\n",
       "      <td>1097</td>\n",
       "      <td>539</td>\n",
       "      <td>326</td>\n",
       "      <td>232</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>1</th>\n",
       "      <td>England</td>\n",
       "      <td>1086</td>\n",
       "      <td>623</td>\n",
       "      <td>206</td>\n",
       "      <td>257</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>2</th>\n",
       "      <td>Argentina</td>\n",
       "      <td>1062</td>\n",
       "      <td>586</td>\n",
       "      <td>219</td>\n",
       "      <td>257</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>3</th>\n",
       "      <td>Brazil</td>\n",
       "      <td>1055</td>\n",
       "      <td>669</td>\n",
       "      <td>170</td>\n",
       "      <td>216</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>4</th>\n",
       "      <td>Germany</td>\n",
       "      <td>1027</td>\n",
       "      <td>595</td>\n",
       "      <td>219</td>\n",
       "      <td>213</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>5</th>\n",
       "      <td>South Korea</td>\n",
       "      <td>1003</td>\n",
       "      <td>536</td>\n",
       "      <td>215</td>\n",
       "      <td>252</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>6</th>\n",
       "      <td>Hungary</td>\n",
       "      <td>1002</td>\n",
       "      <td>469</td>\n",
       "      <td>312</td>\n",
       "      <td>221</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>7</th>\n",
       "      <td>Mexico</td>\n",
       "      <td>997</td>\n",
       "      <td>510</td>\n",
       "      <td>258</td>\n",
       "      <td>229</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>8</th>\n",
       "      <td>Uruguay</td>\n",
       "      <td>966</td>\n",
       "      <td>427</td>\n",
       "      <td>302</td>\n",
       "      <td>237</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>9</th>\n",
       "      <td>France</td>\n",
       "      <td>931</td>\n",
       "      <td>474</td>\n",
       "      <td>262</td>\n",
       "      <td>195</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>10</th>\n",
       "      <td>Italy</td>\n",
       "      <td>889</td>\n",
       "      <td>474</td>\n",
       "      <td>173</td>\n",
       "      <td>242</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>11</th>\n",
       "      <td>Poland</td>\n",
       "      <td>888</td>\n",
       "      <td>383</td>\n",
       "      <td>281</td>\n",
       "      <td>224</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>12</th>\n",
       "      <td>Switzerland</td>\n",
       "      <td>880</td>\n",
       "      <td>315</td>\n",
       "      <td>363</td>\n",
       "      <td>202</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>13</th>\n",
       "      <td>Netherlands</td>\n",
       "      <td>875</td>\n",
       "      <td>451</td>\n",
       "      <td>227</td>\n",
       "      <td>197</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>14</th>\n",
       "      <td>Denmark</td>\n",
       "      <td>870</td>\n",
       "      <td>400</td>\n",
       "      <td>287</td>\n",
       "      <td>183</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>15</th>\n",
       "      <td>Norway</td>\n",
       "      <td>868</td>\n",
       "      <td>327</td>\n",
       "      <td>347</td>\n",
       "      <td>194</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>16</th>\n",
       "      <td>Thailand</td>\n",
       "      <td>863</td>\n",
       "      <td>339</td>\n",
       "      <td>320</td>\n",
       "      <td>204</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>17</th>\n",
       "      <td>Austria</td>\n",
       "      <td>857</td>\n",
       "      <td>364</td>\n",
       "      <td>309</td>\n",
       "      <td>184</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>18</th>\n",
       "      <td>Belgium</td>\n",
       "      <td>849</td>\n",
       "      <td>379</td>\n",
       "      <td>290</td>\n",
       "      <td>180</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>19</th>\n",
       "      <td>Scotland</td>\n",
       "      <td>847</td>\n",
       "      <td>400</td>\n",
       "      <td>265</td>\n",
       "      <td>182</td>\n",
       "    </tr>\n",
       "  </tbody>\n",
       "</table>\n",
       "</div>"
      ],
      "text/plain": [
       "        Country  Number of Matches  Wins Home  Wins Guest  Ties\n",
       "0        Sweden               1097        539         326   232\n",
       "1       England               1086        623         206   257\n",
       "2     Argentina               1062        586         219   257\n",
       "3        Brazil               1055        669         170   216\n",
       "4       Germany               1027        595         219   213\n",
       "5   South Korea               1003        536         215   252\n",
       "6       Hungary               1002        469         312   221\n",
       "7        Mexico                997        510         258   229\n",
       "8       Uruguay                966        427         302   237\n",
       "9        France                931        474         262   195\n",
       "10        Italy                889        474         173   242\n",
       "11       Poland                888        383         281   224\n",
       "12  Switzerland                880        315         363   202\n",
       "13  Netherlands                875        451         227   197\n",
       "14      Denmark                870        400         287   183\n",
       "15       Norway                868        327         347   194\n",
       "16     Thailand                863        339         320   204\n",
       "17      Austria                857        364         309   184\n",
       "18      Belgium                849        379         290   180\n",
       "19     Scotland                847        400         265   182"
      ]
     },
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "# Create a \"win balance\" dataset with Country, Number of Matches, Wins Home, Wins Away, Ties\n",
    "from collections import defaultdict\n",
    "\n",
    "# Initialize dictionaries to track matches and wins\n",
    "country_stats = defaultdict(lambda: {'matches': 0, 'wins_home': 0, 'wins_away': 0, 'ties': 0})\n",
    "\n",
    "# Process all matches\n",
    "for idx, row in df.iterrows():\n",
    "    home_team = row['home_team']\n",
    "    away_team = row['away_team']\n",
    "    home_score = row['home_score']\n",
    "    away_score = row['away_score']\n",
    "    \n",
    "    # Count matches\n",
    "    country_stats[home_team]['matches'] += 1\n",
    "    country_stats[away_team]['matches'] += 1\n",
    "    \n",
    "    # Count wins and ties\n",
    "    if home_score > away_score:\n",
    "        country_stats[home_team]['wins_home'] += 1\n",
    "        country_stats[away_team]['wins_away'] += 1\n",
    "    elif away_score > home_score:\n",
    "        country_stats[away_team]['wins_home'] += 1\n",
    "        country_stats[home_team]['wins_away'] += 1\n",
    "    else:  # Tie\n",
    "        country_stats[home_team]['ties'] += 1\n",
    "        country_stats[away_team]['ties'] += 1\n",
    "\n",
    "# Create the result dataframe from the top 20 countries\n",
    "countries_list = []\n",
    "matches_list = []\n",
    "wins_home_list = []\n",
    "wins_away_list = []\n",
    "ties_list = []\n",
    "\n",
    "for country in result_df['Country']:\n",
    "    countries_list.append(country)\n",
    "    matches_list.append(country_stats[country]['matches'])\n",
    "    wins_home_list.append(country_stats[country]['wins_home'])\n",
    "    wins_away_list.append(country_stats[country]['wins_away'])\n",
    "    ties_list.append(country_stats[country]['ties'])\n",
    "\n",
    "win_balance_df = pd.DataFrame({\n",
    "    'Country': countries_list,\n",
    "    'Number of Matches': matches_list,\n",
    "    'Wins Home': wins_home_list,\n",
    "    'Wins Guest': wins_away_list,\n",
    "    'Ties': ties_list\n",
    "})\n",
    "\n",
    "win_balance_df"
   ]
  },
  {
   "cell_type": "test",
   "execution_count": null,
   "id": "5db131fc",
   "metadata": {
    "code_timestamp": "2026-03-03T09:55:17.658935",
    "explanation": "Check that for all countries above, Wins Home plus Wins Guest plus Ties is equal to Number of Matches. ",
    "explanation_timestamp": "2026-03-03T09:55:15.856467"
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": "✓ All countries have correct match totals: Wins Home + Wins Guest + Ties = Number of Matches\n"
    },
    {
     "name": "stdout",
     "output_type": "stream",
     "text": "The test passed.\n"
    }
   ],
   "source": [
    "# Test that for all countries, Wins Home + Wins Guest + Ties equals Number of Matches\n",
    "for idx, row in win_balance_df.iterrows():\n",
    "    country = row['Country']\n",
    "    total_matches = row['Number of Matches']\n",
    "    wins_home = row['Wins Home']\n",
    "    wins_guest = row['Wins Guest']\n",
    "    ties = row['Ties']\n",
    "    \n",
    "    calculated_total = wins_home + wins_guest + ties\n",
    "    \n",
    "    assert calculated_total == total_matches, \\\n",
    "        f\"{country}: Wins Home ({wins_home}) + Wins Guest ({wins_guest}) + Ties ({ties}) = {calculated_total}, but Number of Matches is {total_matches}\"\n",
    "\n",
    "print(\"✓ All countries have correct match totals: Wins Home + Wins Guest + Ties = Number of Matches\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "id": "7171f80b",
   "metadata": {
    "code_timestamp": "2026-03-03T10:24:59.624492",
    "explanation": "Display the 20 countries with the highest ratio of wins guest to wins home. ",
    "explanation_timestamp": "2026-03-03T10:24:57.795497",
    "name": "guest_wins_ratio",
    "variables": {
     "all_matches": {
      "dtype": "float64",
      "len": 333,
      "type": "Series"
     },
     "away_matches": {
      "dtype": "int64",
      "len": 318,
      "type": "Series"
     },
     "away_score": {
      "type": "int"
     },
     "away_team": {
      "type": "str"
     },
     "countries_list": {
      "len": 20,
      "type": "list"
     },
     "country": {
      "type": "str"
     },
     "country_stats": {
      "len": 333,
      "type": "defaultdict"
     },
     "df": {
      "columns": [
       {
        "dtype": "str",
        "name": "date"
       },
       {
        "dtype": "str",
        "name": "home_team"
       },
       {
        "dtype": "str",
        "name": "away_team"
       },
       {
        "dtype": "int64",
        "name": "home_score"
       },
       {
        "dtype": "int64",
        "name": "away_score"
       },
       {
        "dtype": "str",
        "name": "tournament"
       },
       {
        "dtype": "str",
        "name": "city"
       },
       {
        "dtype": "str",
        "name": "country"
       },
       {
        "dtype": "bool",
        "name": "neutral"
       }
      ],
      "shape": [
       49071,
       9
      ],
      "type": "DataFrame"
     },
     "home_matches": {
      "dtype": "int64",
      "len": 325,
      "type": "Series"
     },
     "home_score": {
      "type": "int"
     },
     "home_team": {
      "type": "str"
     },
     "idx": {
      "type": "int"
     },
     "matches_list": {
      "len": 20,
      "type": "list"
     },
     "result_df": {
      "columns": [
       {
        "dtype": "str",
        "name": "Country"
       },
       {
        "dtype": "int64",
        "name": "Number of Matches"
       }
      ],
      "shape": [
       20,
       2
      ],
      "type": "DataFrame"
     },
     "row": {
      "dtype": "object",
      "len": 9,
      "type": "Series"
     },
     "ties_list": {
      "len": 20,
      "type": "list"
     },
     "top_20": {
      "dtype": "float64",
      "len": 20,
      "type": "Series"
     },
     "win_balance_df": {
      "columns": [
       {
        "dtype": "str",
        "name": "Country"
       },
       {
        "dtype": "int64",
        "name": "Number of Matches"
       },
       {
        "dtype": "int64",
        "name": "Wins Home"
       },
       {
        "dtype": "int64",
        "name": "Wins Guest"
       },
       {
        "dtype": "int64",
        "name": "Ties"
       },
       {
        "dtype": "float64",
        "name": "Win Guest/Home Ratio"
       }
      ],
      "shape": [
       20,
       6
      ],
      "type": "DataFrame"
     },
     "win_balance_df_sorted": {
      "columns": [
       {
        "dtype": "str",
        "name": "Country"
       },
       {
        "dtype": "int64",
        "name": "Number of Matches"
       },
       {
        "dtype": "int64",
        "name": "Wins Home"
       },
       {
        "dtype": "int64",
        "name": "Wins Guest"
       },
       {
        "dtype": "int64",
        "name": "Ties"
       },
       {
        "dtype": "float64",
        "name": "Win Guest/Home Ratio"
       }
      ],
      "shape": [
       20,
       6
      ],
      "type": "DataFrame"
     },
     "wins_away_list": {
      "len": 20,
      "type": "list"
     },
     "wins_home_list": {
      "len": 20,
      "type": "list"
     }
    }
   },
   "outputs": [
    {
     "data": {
      "text/html": [
       "<div>\n",
       "<style scoped>\n",
       "    .dataframe tbody tr th:only-of-type {\n",
       "        vertical-align: middle;\n",
       "    }\n",
       "\n",
       "    .dataframe tbody tr th {\n",
       "        vertical-align: top;\n",
       "    }\n",
       "\n",
       "    .dataframe thead th {\n",
       "        text-align: right;\n",
       "    }\n",
       "</style>\n",
       "<table border=\"1\" class=\"dataframe\">\n",
       "  <thead>\n",
       "    <tr style=\"text-align: right;\">\n",
       "      <th></th>\n",
       "      <th>Country</th>\n",
       "      <th>Wins Home</th>\n",
       "      <th>Wins Guest</th>\n",
       "      <th>Win Guest/Home Ratio</th>\n",
       "    </tr>\n",
       "  </thead>\n",
       "  <tbody>\n",
       "    <tr>\n",
       "      <th>12</th>\n",
       "      <td>Switzerland</td>\n",
       "      <td>315</td>\n",
       "      <td>363</td>\n",
       "      <td>1.152381</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>15</th>\n",
       "      <td>Norway</td>\n",
       "      <td>327</td>\n",
       "      <td>347</td>\n",
       "      <td>1.061162</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>16</th>\n",
       "      <td>Thailand</td>\n",
       "      <td>339</td>\n",
       "      <td>320</td>\n",
       "      <td>0.943953</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>17</th>\n",
       "      <td>Austria</td>\n",
       "      <td>364</td>\n",
       "      <td>309</td>\n",
       "      <td>0.848901</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>18</th>\n",
       "      <td>Belgium</td>\n",
       "      <td>379</td>\n",
       "      <td>290</td>\n",
       "      <td>0.765172</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>11</th>\n",
       "      <td>Poland</td>\n",
       "      <td>383</td>\n",
       "      <td>281</td>\n",
       "      <td>0.733681</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>14</th>\n",
       "      <td>Denmark</td>\n",
       "      <td>400</td>\n",
       "      <td>287</td>\n",
       "      <td>0.717500</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>8</th>\n",
       "      <td>Uruguay</td>\n",
       "      <td>427</td>\n",
       "      <td>302</td>\n",
       "      <td>0.707260</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>6</th>\n",
       "      <td>Hungary</td>\n",
       "      <td>469</td>\n",
       "      <td>312</td>\n",
       "      <td>0.665245</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>19</th>\n",
       "      <td>Scotland</td>\n",
       "      <td>400</td>\n",
       "      <td>265</td>\n",
       "      <td>0.662500</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>0</th>\n",
       "      <td>Sweden</td>\n",
       "      <td>539</td>\n",
       "      <td>326</td>\n",
       "      <td>0.604824</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>9</th>\n",
       "      <td>France</td>\n",
       "      <td>474</td>\n",
       "      <td>262</td>\n",
       "      <td>0.552743</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>7</th>\n",
       "      <td>Mexico</td>\n",
       "      <td>510</td>\n",
       "      <td>258</td>\n",
       "      <td>0.505882</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>13</th>\n",
       "      <td>Netherlands</td>\n",
       "      <td>451</td>\n",
       "      <td>227</td>\n",
       "      <td>0.503326</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>5</th>\n",
       "      <td>South Korea</td>\n",
       "      <td>536</td>\n",
       "      <td>215</td>\n",
       "      <td>0.401119</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>2</th>\n",
       "      <td>Argentina</td>\n",
       "      <td>586</td>\n",
       "      <td>219</td>\n",
       "      <td>0.373720</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>4</th>\n",
       "      <td>Germany</td>\n",
       "      <td>595</td>\n",
       "      <td>219</td>\n",
       "      <td>0.368067</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>10</th>\n",
       "      <td>Italy</td>\n",
       "      <td>474</td>\n",
       "      <td>173</td>\n",
       "      <td>0.364979</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>1</th>\n",
       "      <td>England</td>\n",
       "      <td>623</td>\n",
       "      <td>206</td>\n",
       "      <td>0.330658</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>3</th>\n",
       "      <td>Brazil</td>\n",
       "      <td>669</td>\n",
       "      <td>170</td>\n",
       "      <td>0.254111</td>\n",
       "    </tr>\n",
       "  </tbody>\n",
       "</table>\n",
       "</div>"
      ],
      "text/plain": [
       "        Country  Wins Home  Wins Guest  Win Guest/Home Ratio\n",
       "12  Switzerland        315         363              1.152381\n",
       "15       Norway        327         347              1.061162\n",
       "16     Thailand        339         320              0.943953\n",
       "17      Austria        364         309              0.848901\n",
       "18      Belgium        379         290              0.765172\n",
       "11       Poland        383         281              0.733681\n",
       "14      Denmark        400         287              0.717500\n",
       "8       Uruguay        427         302              0.707260\n",
       "6       Hungary        469         312              0.665245\n",
       "19     Scotland        400         265              0.662500\n",
       "0        Sweden        539         326              0.604824\n",
       "9        France        474         262              0.552743\n",
       "7        Mexico        510         258              0.505882\n",
       "13  Netherlands        451         227              0.503326\n",
       "5   South Korea        536         215              0.401119\n",
       "2     Argentina        586         219              0.373720\n",
       "4       Germany        595         219              0.368067\n",
       "10        Italy        474         173              0.364979\n",
       "1       England        623         206              0.330658\n",
       "3        Brazil        669         170              0.254111"
      ]
     },
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "win_balance_df['Win Guest/Home Ratio'] = win_balance_df['Wins Guest'] / win_balance_df['Wins Home']\n",
    "win_balance_df_sorted = win_balance_df.sort_values('Win Guest/Home Ratio', ascending=False)\n",
    "win_balance_df_sorted[['Country', 'Wins Home', 'Wins Guest', 'Win Guest/Home Ratio']]"
   ]
  }
 ],
 "metadata": {
  "ai_instructions": "",
  "input_files": [],
  "is_locked": false,
  "last_valid_code_cell": 4,
  "last_valid_output": 4,
  "last_valid_test_cell": 3,
  "missing_input_files": [],
  "share_output_with_ai": true
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
