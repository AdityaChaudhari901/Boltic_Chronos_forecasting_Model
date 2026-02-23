"""
Flask API wrapper for Chronos-2 Inventory Forecasting Model
Strict Compliance: Uses Chronos2Pipeline.predict_df()
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import os
import io
import sys

# Configuration / Constants
DEMAND_INCREASE_THRESHOLD = 1.2
DEMAND_DECREASE_THRESHOLD = 0.8
PEAK_DEMAND_THRESHOLD = 1.5

app = Flask(__name__)
CORS(app)

# Global model instance
pipeline = None

def load_model():
    """Load model from local fine-tuned directory or fallback to base."""
    global pipeline
    if pipeline is None:
        # Lazy imports to prevent startup timeout
        print("Lazy loading heavy dependencies (torch, chronos)...")
        import torch
        from chronos import Chronos2Pipeline
        
        model_name = "finetuned_chronos_forecasting"
        model_path = f"./{model_name}"
        
        if not os.path.exists(model_path):
            print(f"Local model not found at {model_path}, utilizing base model 'amazon/chronos-2'...")
            model_path = "amazon/chronos-2"
        
        print(f"Loading model from {model_path} into memory...")
        try:
            # Explicitly target CPU and use low_cpu_mem_usage to prevent OOM
            pipeline = Chronos2Pipeline.from_pretrained(
                model_path,
                device_map="cpu", 
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True
            )
            print("✅ Model loaded successfully!")
        except Exception as e:
            print(f"❌ Error during model loading: {e}")
            import traceback
            traceback.print_exc()
            raise
    return pipeline

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'model_loaded': pipeline is not None})

@app.route('/forecast/csv', methods=['POST'])
def forecast_csv():
    """
    Generate forecasts from CSV.
    Expected columns: id (SKU), timestamp, target (demand), [covariates...]
    """
    try:
        # Load Model
        cols_model = load_model()
        
        # Parse Request
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400
            
        # prediction_length from query param (default 30)
        try:
            prediction_length = int(request.args.get('prediction_length', 30))
        except:
            prediction_length = 30

        # Read CSV
        df = pd.read_csv(file)
        
        # Column standardization
        # Map known variations to canonical names
        column_map = {
            'unique_id': 'id',
            'ds': 'timestamp',
            'y': 'target',
            'demand': 'target',
            'State_date': 'timestamp',
            'sku_code': 'id_candidate_1',
            'seller_identifier': 'id_candidate_2'
        }
        df = df.rename(columns=column_map)
        
        # Smart ID Selection
        # If 'id' is not present, check candidates
        if 'id' not in df.columns:
            if 'id_candidate_2' in df.columns:
                 # Prefer seller_identifier as we know sku_code can be empty
                 df['id'] = df['id_candidate_2']
            elif 'id_candidate_1' in df.columns:
                 df['id'] = df['id_candidate_1']
        
        # Ensure timestamp type
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True).dt.tz_convert(None).dt.normalize()
        
        # Validation
        if 'id' not in df.columns or 'timestamp' not in df.columns:
            return jsonify({'error': f"CSV must contain 'id' (or sku_code/seller_identifier) and 'timestamp' (or State_date) columns. Found: {df.columns.tolist()}"}), 400
            
        # ID Filling (if some rows are NaN)
        if df['id'].isna().all():
             # If mapped ID column is all empty (like sku_code), try fallback
             if 'id_candidate_2' in df.columns:
                 df['id'] = df['id_candidate_2']
        
        # Identify "Target" Column
        # If 'target' column exists, use it.
        # If NOT, and we have transactional data (no explicit target), we AGGREGATE.
        target_col = 'target'
        if 'target' not in df.columns:
            print("ℹ️ 'target' column not found. Aggregating daily counts per ID.")
            # Filter for delivery_done if column exists
            if 'cur_state' in df.columns:
                df = df[df['cur_state'] == 'delivery_done']
            
            # Aggregate
            df = df.groupby(['id', 'timestamp']).size().reset_index(name='target')
            
        if 'target' not in df.columns:
             return jsonify({'error': "CSV must contain 'target' column or be capable of aggregation"}), 400

        # Split into History and Future
        # Logic: 
        # Mode A: User uploads only history. Target is present and valid. Future DF is None.
        # Mode B: User uploads history + future rows. Future rows have NaN target.
        
        # We process per SKU or global? predict_df takes a DF. 
        # Ideally we pass the whole DF and let it handle grouping.
        # However, to support specific logic:
        # 1. Separate contexts where target is valid -> df
        # 2. Separate contexts where target is NaN -> future_df (if exists)
        
        # Filter for rows with valid target
        history_df = df.dropna(subset=[target_col]).copy()
        
        # --- INVENTORY PARAMS EXTRACTION ---
        # Capture per-SKU params before we melt/pivot and potentially lose them
        inventory_params = {}
        
        # Check for inventory columns or use defaults
        # defaults: lead_time=14, service_level=0.95 (implied by using P90), on_hand=0
        if 'id' in df.columns:
            # Drop duplicates to get unique SKU params (assuming static per SKU for this upload)
            param_cols = ['id']
            for col in ['on_hand', 'on_hand_inventory', 'lead_time', 'lead_time_days', 'pipeline', 'incoming_stock']:
                if col in df.columns:
                    param_cols.append(col)
            
            # create a lookup
            start_params = df[param_cols].drop_duplicates(subset=['id']).set_index('id')
            inventory_params = start_params.to_dict('index')

        # --- DENSIFICATION & ROBUSTNESS ---
        # Ensure every SKU has a continuous daily time series.
        # This fixes "length=1" errors for sparse data.
        
        # 1. Densify
        # Pivot to get complete date range
        pivot_df = history_df.pivot_table(index='timestamp', columns='id', values='target', aggfunc='sum')
        
        # Reindex to fill missing dates globally
        all_dates = pd.date_range(start=pivot_df.index.min(), end=pivot_df.index.max(), freq='D')
        pivot_df = pivot_df.reindex(all_dates, fill_value=0)
        pivot_df = pivot_df.fillna(0)
        
        # Melt back
        history_df = pivot_df.reset_index().melt(id_vars='index', var_name='id', value_name='target')
        history_df = history_df.rename(columns={'index': 'timestamp'})
        
        # 2. Filter Short Series
        # Chronos requires at least 3 context points
        sku_counts = history_df['id'].value_counts()
        valid_skus = sku_counts[sku_counts >= 3].index
        trash_skus = sku_counts[sku_counts < 3].index
        
        if len(trash_skus) > 0:
            print(f"⚠️ Dropped {len(trash_skus)} SKUs with < 3 data points: {trash_skus[:5].tolist()}...")
            history_df = history_df[history_df['id'].isin(valid_skus)]
            
        if len(history_df) == 0:
             return jsonify({'error': "Not enough data points per SKU (minimum 3 required) after processing."}), 400
             
        # ----------------------------------

        # Check for future rows (target is NaN)
        # These will contain future covariates
        future_rows = df[df[target_col].isna()].copy()
        
        future_df = None
        if len(future_rows) > 0:
            # We have future covariates!
            # Drop target col from future_df as it's not needed (it's NaN)
            future_df = future_rows.drop(columns=[target_col])
            print(f"ℹ️ Found {len(future_df)} future rows with covariates.")
        
        # Call predict_df
        # This returns a DataFrame with predictions
        # It handles grouping by 'id' automatically
        forecast_df = cols_model.predict_df(
            history_df,
            future_df=future_df, # Can be None
            prediction_length=prediction_length,
            quantile_levels=[0.1, 0.5, 0.9],
            id_column="id",
            timestamp_column="timestamp",
            target=target_col
        )
        
        # Format Response
        # Group by SKU and build JSON
        results = []
        for sku_id, group in forecast_df.groupby("id"):
            # Sort by timestamp just in case
            group = group.sort_values("timestamp")
            
            # Extract arrays - Round to nearest Int and Clip Negatives
            p10 = [max(0, int(round(x))) for x in group["0.1"].tolist()]
            p50 = [max(0, int(round(x))) for x in group["0.5"].tolist()]
            p90 = [max(0, int(round(x))) for x in group["0.9"].tolist()]
            timestamps_str = group["timestamp"].dt.strftime('%Y-%m-%d').tolist()
            
            # Forecast Totals (over prediction horizon, e.g. 30 days)
            total_p50 = sum(p50)
            total_p90 = sum(p90)
            
            # --- POLICY LAYER ---
            # Defaults
            sku_params = inventory_params.get(sku_id, {})
            # Look for keys
            on_hand = sku_params.get('on_hand') or sku_params.get('on_hand_inventory', 0)
            lead_time = sku_params.get('lead_time') or sku_params.get('lead_time_days', 7) # Default 7 days
            pipeline_stock = sku_params.get('pipeline') or sku_params.get('incoming_stock', 0)
            
            # 1. Lead Time Demand (Forecast over next LT days)
            # We generated `prediction_length` days. We take the first `lead_time` days.
            lt_idx = min(len(p50), int(lead_time))
            lead_time_demand = sum(p50[:lt_idx])
            
            # 2. Safety Stock
            # Heuristic: Variability over Lead Time. 
            # We use the difference between Aggressive (P90) and Median (P50) over the LT window as the safety buffer.
            # This accounts for the model's uncertainty about demand.
            lt_p90 = sum(p90[:lt_idx])
            safety_stock = lt_p90 - lead_time_demand
            
            # 3. Reorder Point
            reorder_point = lead_time_demand + safety_stock
            
            # 4. Refill Quantity
            # Refill = Max(0, Reorder Point - (OnHand + Pipeline))
            inventory_position = on_hand + pipeline_stock
            refill_qty = max(0, reorder_point - inventory_position)
            
            # Use the last date of prediction as the "By when" date
            fulfillment_date = timestamps_str[-1] if timestamps_str else "N/A"

            results.append({
                "SKU": str(sku_id),
                "Expected_Demand": int(total_p50),
                "aggressive_plan": int(total_p90),
                "conservative_plan": int(sum(p10)),
                "Policy": {
                    "Lead_Time_Days": int(lead_time),
                    "On_Hand": int(on_hand),
                    "Safety_Stock": int(safety_stock),
                    "Reorder_Point": int(reorder_point),
                    "Refill_Qty": int(refill_qty)
                },
                "By_when_it_should_be_fullfilled": fulfillment_date
            })
            
        return jsonify({"forecasts": results})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    load_model()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)