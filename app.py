import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Ticket Data Cleaning & Feature Analysis", layout="wide")

st.title("🎫 Ticket Data Cleaning & Feature Analysis Pipeline")
st.write("Upload your ticket dataset to clean, map event types (dropping original type), exclude 'sw-client' tenants, isolate un-actioned tickets, and extract user & action drill-downs.")

uploaded_file = st.file_uploader("Upload Raw Ticket CSV", type=["csv"])

TYPE_MAPPING = {
    'e5.platform.app.state.Reprocessing': 'State Mgmt',
    'e5.platform.event.workflow.NOT_STARTED': 'WF Not Started',
    'e5.platform.app.workers.PAUSE/RESUME': 'Pause/Resume',
    'e5.platform.app.workers.Trigger.Workflow': 'Trigger WF',
    'e5.platform.app.workers.Enable/Disable': 'Enable/Disable WF',
    'e5.platform.app.workers.Terminate': 'Terminate WF',
    'e5.autohub.event.1.0.resource.NOT_AVAILABLE': 'Resource Unavailable',
    'e5.platform.app.workers.ScaleAppWorkers': 'Scale App Workers',
    'e5.errorselection.credential.management': 'Credential Management',
    'e5.platform.app.workers.SafeDeployment': 'Safe Deployment',
}

def process_ticket_data(df):
    # 0. Count and filter out rows where Tenant Name equals 'sw-client' (case-insensitive)
    if 'Tenant Name' in df.columns:
        sw_client_mask = df['Tenant Name'].astype(str).str.strip().str.lower().eq('sw-client')
        sw_client_count = sw_client_mask.sum()
        df = df[~sw_client_mask].copy()
    else:
        sw_client_count = 0

    # 1. Rename 'Incident Id' to 'Event Id'
    if 'Incident Id' in df.columns:
        df = df.rename(columns={'Incident Id': 'Event Id'})
        
    # 2. Map Type column and drop the raw/original 'Type' column
    if 'Type' in df.columns:
        df['Mapped Ticket Type'] = df['Type'].map(TYPE_MAPPING).fillna(df['Type'])
        df = df.drop(columns=['Type'])
    
    # 3. Separate tickets where no action was taken
    if 'Who took actions' in df.columns:
        df['Who took actions_clean'] = df['Who took actions'].astype(str).str.strip()
        no_action_mask = df['Who took actions_clean'].isin(['nan', '', 'None']) | df['Who took actions'].isna()
        
        df_no_action = df[no_action_mask].drop(columns=['Who took actions_clean'], errors='ignore').copy()
        df_actioned = df[~no_action_mask].drop(columns=['Who took actions_clean'], errors='ignore').copy()
    else:
        df_no_action = pd.DataFrame()
        df_actioned = df.copy()
        
    # 4. Parse and explode human users (removing 'ARE System' and 'Original Type')
    parsed_user_rows = []
    for _, row in df_actioned.iterrows():
        raw_users = str(row.get('Who took actions', '')).split(',')
        cleaned_users = [u.strip() for u in raw_users if u.strip()]
        
        human_users = [u for u in cleaned_users if u.lower() != 'are system']
        if not human_users:
            continue
            
        for user in human_users:
            parsed_user_rows.append({
                'Date Created': row.get('Date Created'),
                'Are Ticket Id': row.get('Are Ticket Id'),
                'Event Id': row.get('Event Id'),
                'Tenant Name': row.get('Tenant Name'),
                'Workflow Name': row.get('Workflow Name'),
                'Mapped Ticket Type': row.get('Mapped Ticket Type'),
                'User': user,
                'Actions Taken': row.get('Actions')
            })
    df_feature_analysis = pd.DataFrame(parsed_user_rows)

    # 5. Explode both Users AND Actions (ensuring no duplicates per Event Id + User + Action)
    exploded_action_rows = []
    for _, row in df_actioned.iterrows():
        raw_users = str(row.get('Who took actions', '')).split(',')
        cleaned_users = [u.strip() for u in raw_users if u.strip()]
        human_users = [u for u in cleaned_users if u.lower() != 'are system']
        
        raw_actions = str(row.get('Actions', '')).split(',')
        cleaned_actions = [a.strip() for a in raw_actions if a.strip()]
        
        if not human_users or not cleaned_actions:
            continue
            
        for user in human_users:
            for action in cleaned_actions:
                exploded_action_rows.append({
                    'Date Created': row.get('Date Created'),
                    'Are Ticket Id': row.get('Are Ticket Id'),
                    'Event Id': row.get('Event Id'),
                    'Tenant Name': row.get('Tenant Name'),
                    'Workflow Name': row.get('Workflow Name'),
                    'Mapped Ticket Type': row.get('Mapped Ticket Type'),
                    'User': user,
                    'Action': action
                })
                
    df_actions_exploded = pd.DataFrame(exploded_action_rows)
    if not df_actions_exploded.empty:
        df_actions_exploded = df_actions_exploded.drop_duplicates(subset=['Event Id', 'User', 'Action'])

    return df_actioned, df_no_action, df_feature_analysis, df_actions_exploded, sw_client_count

if uploaded_file is not None:
    raw_df = pd.read_csv(uploaded_file)
    
    df_actioned, df_no_action, df_feature_analysis, df_actions_exploded, sw_client_count = process_ticket_data(raw_df)
    
    st.success("Processing Complete!")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Original Rows", len(raw_df))
    col2.metric("Deleted sw-client", sw_client_count)
    col3.metric("Feature Analysis", len(df_feature_analysis))
    col4.metric("Action Exploded", len(df_actions_exploded))
    col5.metric("No Action", len(df_no_action))
    
    st.divider()
    
    tab1, tab2, tab3 = st.tabs([
        "📊 Feature Success Analysis", 
        "🔍 Exploded Actions Dataset", 
        "⚠️ No Action Taken"
    ])
    
    with tab1:
        st.subheader("User-Level Feature Engagement")
        st.dataframe(df_feature_analysis, use_container_width=True)
        st.download_button(
            label="📥 Download Feature Success CSV",
            data=df_feature_analysis.to_csv(index=False).encode('utf-8'),
            file_name="feature_success_analysis_dataset.csv",
            mime="text/csv"
        )
        
    with tab2:
        st.subheader("User & Action Exploded Dataset (Deduplicated per Event Id)")
        st.dataframe(df_actions_exploded, use_container_width=True)
        st.download_button(
            label="📥 Download Exploded Actions CSV",
            data=df_actions_exploded.to_csv(index=False).encode('utf-8'),
            file_name="user_actions_exploded_dataset.csv",
            mime="text/csv"
        )
        
    with tab3:
        st.subheader("Un-actioned Tickets")
        st.dataframe(df_no_action, use_container_width=True)
        st.download_button(
            label="📥 Download No Action Taken CSV",
            data=df_no_action.to_csv(index=False).encode('utf-8'),
            file_name="no_action_taken_dataset.csv",
            mime="text/csv"
        )