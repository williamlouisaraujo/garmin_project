import streamlit as st

from src.auth import require_password
from src.garmin_client import fetch_activities, fetch_all_activities
from src.storage import get_accounts, get_last_sync, save_accounts, save_activities

st.set_page_config(
    page_title="Garmin Dashboard",
    page_icon="🏃",
    layout="wide",
)

require_password()

st.title("🔗 Connexion & Synchronisation")
st.caption("Gérez vos comptes Garmin Connect et synchronisez vos activités.")

# ── Chargement des comptes ────────────────────────────────────────────────────
try:
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Impossible de se connecter à Supabase : {exc}")
    st.info("Vérifiez que SUPABASE_URL et SUPABASE_KEY sont configurées dans les Secrets Streamlit Cloud.")
    st.stop()

# ── Options de synchronisation ────────────────────────────────────────────────
full_sync = st.toggle(
    "Synchronisation complète (tout l'historique)",
    value=False,
    help="Récupère toutes vos activités en paginant l'API Garmin. Peut prendre plusieurs minutes.",
)

st.divider()

# ── Liste des comptes configurés ──────────────────────────────────────────────
st.subheader("Comptes Garmin")

if not accounts:
    st.info("Aucun compte configuré. Ajoutez un compte ci-dessous.")
else:
    for i, account in enumerate(accounts):
        label = account.get("label") or account["email"]
        last_sync = get_last_sync(account["email"])

        with st.container(border=True):
            col_info, col_sync, col_del = st.columns([5, 2, 1])

            with col_info:
                st.markdown(f"**{label}**")
                st.caption(f"{account['email']} — Dernière synchro : {last_sync}")

            with col_sync:
                if st.button("🔄 Synchroniser", key=f"sync_{i}", use_container_width=True):
                    if full_sync:
                        progress_bar = st.progress(0, text="Récupération de l'historique…")
                        fetched_count = [0]

                        def update_progress(n: int) -> None:
                            fetched_count[0] = n
                            progress_bar.progress(
                                min(n / 5000, 1.0),
                                text=f"{n} activités récupérées…",
                            )

                        with st.spinner(f"Connexion à {account['email']}…"):
                            try:
                                activities = fetch_all_activities(
                                    account["email"],
                                    account["password"],
                                    progress_callback=update_progress,
                                )
                                progress_bar.empty()
                                count_new = save_activities(activities, garmin_account=account["email"])
                                if count_new > 0:
                                    st.success(f"✅ {count_new} nouvelle(s) activité(s) ajoutée(s) sur {len(activities)} récupérées.")
                                else:
                                    st.info(f"✅ Déjà à jour ({len(activities)} activités vérifiées).")
                                st.rerun()
                            except ValueError as exc:
                                st.error(f"⚠️ {exc}")
                            except Exception as exc:
                                st.error(f"❌ Erreur Garmin Connect : {exc}")
                    else:
                        with st.spinner(f"Connexion à {account['email']}…"):
                            try:
                                activities = fetch_activities(account["email"], account["password"], limit=200)
                                count_new = save_activities(activities, garmin_account=account["email"])
                                if count_new > 0:
                                    st.success(f"✅ {count_new} nouvelle(s) activité(s) ajoutée(s).")
                                else:
                                    st.info("✅ Déjà à jour, aucune nouvelle activité.")
                                st.rerun()
                            except ValueError as exc:
                                st.error(f"⚠️ {exc}")
                            except Exception as exc:
                                st.error(f"❌ Erreur Garmin Connect : {exc}")

            with col_del:
                if st.button("🗑️", key=f"del_{i}", help="Retirer ce compte de la liste"):
                    accounts.pop(i)
                    save_accounts(accounts)
                    st.rerun()

st.divider()

# ── Ajouter un compte ─────────────────────────────────────────────────────────
with st.expander("➕ Ajouter un compte Garmin", expanded=not accounts):
    with st.form("add_account"):
        col_l, col_e, col_p = st.columns(3)
        with col_l:
            label = st.text_input("Label (optionnel)", placeholder="Ex : William, Compte perso…")
        with col_e:
            email = st.text_input("Email Garmin Connect")
        with col_p:
            password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("💾 Enregistrer le compte", use_container_width=True)

    if submitted:
        if not email or not password:
            st.error("Email et mot de passe sont requis.")
        elif any(a["email"] == email for a in accounts):
            st.warning("Ce compte est déjà configuré.")
        else:
            accounts.append({
                "email": email,
                "password": password,
                "label": label.strip() or email,
            })
            save_accounts(accounts)
            st.success(f"✅ Compte **{email}** ajouté.")
            st.rerun()

st.divider()
st.info("👈 Utilisez le menu de gauche pour accéder aux statistiques, activités et tendances.")
