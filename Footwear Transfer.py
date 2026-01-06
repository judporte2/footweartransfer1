import streamlit as st
import pandas as pd
import os
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="Footwear Transfer Tool", layout="wide")
st.title("Footwear Transfer Tool")

# ---------------- CORE LOGIC (UNCHANGED) ----------------
def process_file(df):
    df['Store'] = df['Store'].astype(str).str.strip()

    df['Level1_Key'] = (
        df['Matrix'].astype(str).str.strip()
        + ' - ' + df['Attribute 2'].astype(str).str.strip()
        + ' - ' + df['Attribute 1'].astype(str).str.strip()
    )
    df['Level2_Key'] = df['Level1_Key'] + ' - ' + df['Attribute 3'].astype(str).str.strip()

    inventory = df.groupby(
        [
            'Store',
            'Level1_Key',
            'Level2_Key',
            'Matrix',
            'Manufacturer SKU',
            'Attribute 1',
            'Attribute 2',
            'Attribute 3',
            'Brand'
        ]
    )['Quantity on Hand'].sum().reset_index()

    stores = [
        'Athletic Annex - Nora',
        'Athletic Annex - Carmel',
        'Athletic Annex - Fishers'
    ]
    warehouse = 'Athletic Annex - Expo/Team'
    all_locations = stores + [warehouse]

    inventory_dict = {}
    for _, row in inventory.iterrows():
        inventory_dict[(row['Store'], row['Level2_Key'])] = row['Quantity on Hand']

    def get_qty(store, level2_key):
        return inventory_dict.get((store, level2_key), 0)

    def update_qty(from_store, to_store, level2_key):
        inventory_dict[(from_store, level2_key)] -= 1
        inventory_dict[(to_store, level2_key)] = inventory_dict.get((to_store, level2_key), 0) + 1

    def get_level1_total(store, level1_key):
        return sum(
            qty for (s, l2k), qty in inventory_dict.items()
            if s == store and qty > 0 and str(l2k).startswith(level1_key)
        )

    def store_has_level1(store, level1_key):
        return get_level1_total(store, level1_key) > 0

    def get_best_donor_level1(target_store, level1_key):
        candidates = [
            (donor, get_level1_total(donor, level1_key))
            for donor in all_locations
            if donor != target_store and get_level1_total(donor, level1_key) > 1
        ]
        return max(candidates, key=lambda x: x[1])[0] if candidates else None

    def pick_level2_for_level1(donor, level1_key):
        eligible = [
            (l2k, qty)
            for (s, l2k), qty in inventory_dict.items()
            if s == donor and qty > 0 and str(l2k).startswith(level1_key)
        ]
        return max(eligible, key=lambda x: x[1])[0] if eligible else None

    def get_best_donor_level2(target_store, level2_key):
        eligible = []
        for donor in all_locations:
            if donor == target_store:
                continue
            qty = get_qty(donor, level2_key)
            if (donor == warehouse and qty > 0) or (donor != warehouse and qty > 1):
                eligible.append((donor, qty))
        return max(eligible, key=lambda x: x[1])[0] if eligible else None

    transfers = []

    unique_items = inventory[
        [
            'Level1_Key',
            'Level2_Key',
            'Matrix',
            'Manufacturer SKU',
            'Attribute 1',
            'Attribute 2',
            'Attribute 3',
            'Brand'
        ]
    ].drop_duplicates()

    # -------- LEVEL 1 --------
    for _, item in unique_items.iterrows():
        for store in stores:
            if not store_has_level1(store, item['Level1_Key']):
                donor = get_best_donor_level1(store, item['Level1_Key'])
                if donor:
                    chosen = pick_level2_for_level1(donor, item['Level1_Key'])
                    if chosen:
                        transfers.append({
                            'From Store': donor,
                            'To Store': store,
                            'Brand': item['Brand'],
                            'Matrix': item['Matrix'],
                            'Manufacturer SKU': item['Manufacturer SKU'],
                            'Size': item['Attribute 1'],
                            'Width': item['Attribute 2'],
                            'Color': str(chosen).split(" - ")[-1],
                            'Level': '1'
                        })
                        update_qty(donor, store, chosen)

    # -------- LEVEL 2 --------
    for _, item in unique_items.iterrows():
        for store in stores:
            if get_qty(store, item['Level2_Key']) == 0:
                donor = get_best_donor_level2(store, item['Level2_Key'])
                if donor:
                    transfers.append({
                        'From Store': donor,
                        'To Store': store,
                        'Brand': item['Brand'],
                        'Matrix': item['Matrix'],
                        'Manufacturer SKU': item['Manufacturer SKU'],
                        'Size': item['Attribute 1'],
                        'Width': item['Attribute 2'],
                        'Color': item['Attribute 3'],
                        'Level': '2'
                    })
                    update_qty(donor, store, item['Level2_Key'])

    return pd.DataFrame(transfers)

# ---------------- STREAMLIT UI ----------------
uploaded_file = st.file_uploader(
    "Upload Inventory CSV",
    type=["csv"]
)

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    with st.spinner("Running Footwear Transfer…"):
        transfer_df = process_file(df)

    if transfer_df.empty:
        st.info("No transfers were generated.")
    else:
        st.success("Transfers generated!")

        output = BytesIO()
        today = datetime.today().strftime('%Y-%m-%d')

        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for store in transfer_df['From Store'].unique():
                tab = transfer_df[transfer_df['From Store'] == store]
                tab_name = store.split(' - ')[-1].replace('/', '-')
                tab.to_excel(writer, sheet_name=tab_name, index=False)
                writer.sheets[tab_name].freeze_panes(1, 0)

        st.download_button(
            label="Download Transfer File",
            data=output.getvalue(),
            file_name=f"Footwear_Transfer_{today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
