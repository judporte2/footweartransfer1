import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="Footwear Transfer Tool", layout="wide")
st.title("Footwear Transfer Tool")

def process_file_df(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    # ---------------- CLEAN & PREP ----------------
    df['Store'] = df['Store'].astype(str).str.strip()

    df['Level1_Key'] = (
        df['Matrix'].astype(str).str.strip()
        + ' - ' + df['Attribute 2'].astype(str).str.strip()
        + ' - ' + df['Attribute 1'].astype(str).str.strip()
    )
    df['Level2_Key'] = df['Level1_Key'] + ' - ' + df['Attribute 3'].astype(str).str.strip()

    # ---------------- INVENTORY ----------------
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

    # ---------------- LEVEL 1 HELPERS ----------------
    def get_level1_total(store, level1_key):
        total = 0
        for (s, l2k), qty in inventory_dict.items():
            if s == store and qty > 0 and str(l2k).startswith(level1_key):
                total += qty
        return total

    def store_has_level1(store, level1_key):
        return get_level1_total(store, level1_key) > 0

    def get_best_donor_level1(target_store, level1_key):
        candidates = []
        for donor in all_locations:
            if donor == target_store:
                continue
            total = get_level1_total(donor, level1_key)
            if total > 1:
                candidates.append((donor, total))
        if not candidates:
            return None
        return max(candidates, key=lambda x: x[1])[0]

    def pick_level2_for_level1(donor, level1_key):
        eligible = []
        for (s, l2k), qty in inventory_dict.items():
            if s == donor and qty > 0 and str(l2k).startswith(level1_key):
                eligible.append((l2k, qty))
        if not eligible:
            return None
        return max(eligible, key=lambda x: x[1])[0]

    # ---------------- LEVEL 2 HELPER ----------------
    def get_best_donor_level2(target_store, level2_key):
        eligible = []
        for donor in all_locations:
            if donor == target_store:
                continue
            qty = get_qty(donor, level2_key)
            if donor == warehouse:
                if qty > 0:
                    eligible.append((donor, qty))
            else:
                if qty > 1:
                    eligible.append((donor, qty))
        if not eligible:
            return None
        return max(eligible, key=lambda x: x[1])[0]

    # ---------------- TRANSFERS (raw rows, 1 row per unit) ----------------
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
        level1_key = item['Level1_Key']
        matrix = item['Matrix']
        sku = item['Manufacturer SKU']
        size = item['Attribute 1']
        width = item['Attribute 2']
        brand = item['Brand']

        for store in stores:
            if not store_has_level1(store, level1_key):
                donor = get_best_donor_level1(store, level1_key)
                if donor:
                    chosen_level2 = pick_level2_for_level1(donor, level1_key)
                    if chosen_level2:
                        color = str(chosen_level2).split(" - ")[-1]
                        transfers.append({
                            'From Store': donor,
                            'To Store': store,
                            'Brand': brand,
                            'Matrix': matrix,
                            'Manufacturer SKU': sku,
                            'Size': size,
                            'Width': width,
                            'Color': color,
                            'Level': '1'
                        })
                        update_qty(donor, store, chosen_level2)

    # -------- LEVEL 2 --------
    for _, item in unique_items.iterrows():
        level2_key = item['Level2_Key']
        matrix = item['Matrix']
        sku = item['Manufacturer SKU']
        size = item['Attribute 1']
        width = item['Attribute 2']
        color = item['Attribute 3']
        brand = item['Brand']

        for store in stores:
            if get_qty(store, level2_key) == 0:
                donor = get_best_donor_level2(store, level2_key)
                if donor:
                    transfers.append({
                        'From Store': donor,
                        'To Store': store,
                        'Brand': brand,
                        'Matrix': matrix,
                        'Manufacturer SKU': sku,
                        'Size': size,
                        'Width': width,
                        'Color': color,
                        'Level': '2'
                    })
                    update_qty(donor, store, level2_key)

    if not transfers:
        # Return empty df + empty tabs
        empty = pd.DataFrame(columns=[
            'From Store','To Store','Brand','Matrix','Manufacturer SKU',
            'Size','Width','Color','Quantity to Transfer','Level'
        ])
        return empty, {loc.split(' - ')[-1].replace('/', '-'): empty.copy() for loc in all_locations}

    # ---------------- OUTPUT (THIS IS THE PART YOU CALLED OUT) ----------------
    transfer_df = pd.DataFrame(transfers)

    group_cols = [
        'From Store',
        'To Store',
        'Brand',
        'Matrix',
        'Manufacturer SKU',
        'Size',
        'Width',
        'Color',
        'Level'
    ]

    # ✅ YOUR MISSING LOGIC: quantity = count of unit rows
    transfer_df['Quantity to Transfer'] = (
        transfer_df.groupby(group_cols)['From Store'].transform('count')
    )

    # ✅ de-dupe so each combo appears once with quantity
    transfer_df = transfer_df.drop_duplicates(subset=group_cols)

    # ✅ column order
    transfer_df = transfer_df[
        [
            'From Store',
            'To Store',
            'Brand',
            'Matrix',
            'Manufacturer SKU',
            'Size',
            'Width',
            'Color',
            'Quantity to Transfer',
            'Level'
        ]
    ]

    # ✅ Store tabs for all locations (even empty)
    store_tabs = {}
    for store in all_locations:
        tab = transfer_df[transfer_df['From Store'] == store].copy()
        tab = tab.sort_values(
            by=['Brand', 'Matrix', 'Manufacturer SKU', 'Width', 'Color', 'Size']
        ).reset_index(drop=True)
        tab_name = store.split(' - ')[-1].replace('/', '-')
        store_tabs[tab_name] = tab

    return transfer_df, store_tabs

# ---------------- STREAMLIT UI ----------------
uploaded_file = st.file_uploader("Upload Inventory CSV", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    with st.spinner("Running Footwear Transfer…"):
        transfer_df, store_tabs = process_file_df(df)

    if transfer_df.empty:
        st.info("No transfers were generated.")
    else:
        st.success(f"Transfers generated: {len(transfer_df)} grouped lines")

        st.subheader("Preview (Grouped Transfers)")
        st.dataframe(transfer_df, use_container_width=True)

    # Build Excel in-memory (download)
    output = BytesIO()
    today = datetime.today().strftime('%Y-%m-%d')

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for tab_name, tab_df in store_tabs.items():
            tab_df.to_excel(writer, sheet_name=tab_name[:31], index=False)
            writer.sheets[tab_name[:31]].freeze_panes(1, 0)

    st.download_button(
        label="Download Transfer File (Excel)",
        data=output.getvalue(),
        file_name=f"Footwear_Transfer_{today}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.caption("Upload your inventory CSV to generate transfers.")
