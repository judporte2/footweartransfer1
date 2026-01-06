import pandas as pd
import os
from tkinter import Tk, filedialog, messagebox, Button
from datetime import datetime

def process_file(file_path):
    df = pd.read_csv(file_path)

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

    # ---------------- TRANSFERS ----------------
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
        messagebox.showinfo("No Transfers", "No transfers were generated.")
        return

    # ---------------- OUTPUT ----------------
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

    transfer_df['Quantity to Transfer'] = (
        transfer_df.groupby(group_cols)['From Store'].transform('count')
    )

    transfer_df = transfer_df.drop_duplicates(subset=group_cols)

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

    store_tabs = {}
    for store in all_locations:
        tab = transfer_df[transfer_df['From Store'] == store]
        tab = tab.sort_values(
            by=['Brand', 'Matrix', 'Manufacturer SKU', 'Width', 'Color', 'Size']
        ).reset_index(drop=True)
        tab_name = store.split(' - ')[-1].replace('/', '-')
        store_tabs[tab_name] = tab

    today = datetime.today().strftime('%Y-%m-%d')
    output_file = os.path.join(os.path.dirname(file_path), "Footwear_Transfer_" + today + ".xlsx")

    with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
        for tab_name, tab_df in store_tabs.items():
            tab_df.to_excel(writer, sheet_name=tab_name, index=False)
            writer.sheets[tab_name].freeze_panes(1, 0)

    messagebox.showinfo(
        "Success",
        "Transfer file created:\n" + output_file
    )

# ---------------- GUI ----------------
def choose_file():
    filepath = filedialog.askopenfilename(
        title="Select Inventory CSV",
        filetypes=[("CSV files", "*.csv")]
    )
    if filepath:
        process_file(filepath)

root = Tk()
root.title("Footwear Transfer Tool")
root.geometry("300x150")
root.resizable(False, False)

Button(
    root,
    text="Select Inventory CSV",
    command=choose_file,
    height=2,
    width=25
).pack(expand=True)

root.mainloop()
