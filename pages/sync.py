import streamlit as st

from src.garmin_client import fetch_activities, fetch_all_activities
from src.storage import (
    delete_strava_credentials,
    get_accounts,
    get_last_sync,
    get_strava_credentials,
    save_accounts,
    save_activities,
    save_strava_credentials,
    save_strava_records,
)
from src.strava_client import (
    exchange_code,
    fetch_strava_records,
    get_auth_url,
)

st.title("🔗 Synchronisation")
st.caption("Gérez vos comptes Garmin Connect et Strava, et synchronisez vos activités.")

# ── Chargement des comptes Garmin ─────────────────────────────────────────────
try:
    accounts = get_accounts()
except Exception as exc:
    st.error(f"❌ Impossible de se connecter à Supabase : {exc}")
    st.info("Vérifiez que SUPABASE_URL et SUPABASE_KEY sont configurées dans les Secrets Streamlit Cloud.")
    st.stop()

# ── Options de synchronisation Garmin ────────────────────────────────────────
full_sync = st.toggle(
    "Synchronisation complète (tout l'historique)",
    value=False,
    help="Récupère toutes vos activités en paginant l'API Garmin. Peut prendre plusieurs minutes.",
)

st.divider()

# ── Comptes Garmin ────────────────────────────────────────────────────────────
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

# ── Ajouter un compte Garmin ──────────────────────────────────────────────────
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

# ── Bloc Strava ───────────────────────────────────────────────────────────────
st.subheader("Strava")
st.caption("Connectez votre compte Strava pour récupérer vos records.")

# Détection du retour OAuth Strava (code dans l'URL après autorisation)
strava_code = st.query_params.get("code")
strava_scope = st.query_params.get("scope", "")

if strava_code and "activity:read_all" in strava_scope:
    strava_creds = get_strava_credentials()
    if strava_creds and strava_creds.get("client_id"):
        with st.spinner("Finalisation de la connexion Strava…"):
            try:
                tokens = exchange_code(
                    strava_creds["client_id"],
                    strava_creds["client_secret"],
                    strava_code,
                )
                save_strava_credentials({**strava_creds, **tokens})
                st.query_params.clear()
                st.success("✅ Connexion Strava réussie !")
                st.rerun()
            except Exception as exc:
                st.error(f"❌ Erreur lors de la connexion OAuth Strava : {exc}")
    else:
        st.warning("⚠️ Configurez d'abord vos identifiants Strava ci-dessous.")

strava_creds = get_strava_credentials()
is_connected = bool(strava_creds and strava_creds.get("access_token"))

if is_connected:
    athlete = strava_creds.get("athlete") or {}
    athlete_name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    display_name = athlete_name or f"Athlète #{athlete.get('id', '?')}"

    with st.container(border=True):
        col_info, col_sync, col_del = st.columns([5, 2, 1])

        with col_info:
            st.markdown(f"**{display_name}**")
            st.caption("Strava — Connecté ✅")

        with col_sync:
            if st.button("🔄 Sync records", key="strava_sync", use_container_width=True):
                progress_bar = st.progress(0, text="Récupération des activités Strava…")

                def strava_progress(done: int, total: int) -> None:
                    progress_bar.progress(done / total, text=f"Activité {done}/{total}…")

                with st.spinner("Récupération des records Strava…"):
                    try:
                        records = fetch_strava_records(
                            strava_creds,
                            progress_callback=strava_progress,
                        )
                        progress_bar.empty()
                        if records:
                            save_strava_records(records)
                            st.success(f"✅ {len(records)} distance(s) enregistrée(s) depuis Strava.")
                        else:
                            st.info("ℹ️ Aucun record Strava trouvé sur les activités récentes.")
                    except ValueError as exc:
                        st.error(f"⚠️ {exc}")
                    except RuntimeError as exc:
                        st.error(f"⏱️ {exc}")
                    except Exception as exc:
                        st.error(f"❌ Erreur Strava : {exc}")

        with col_del:
            if st.button("🗑️", key="strava_del", help="Déconnecter Strava"):
                delete_strava_credentials()
                st.rerun()

else:
    # Formulaire de configuration (client_id / client_secret / redirect_uri)
    has_client = bool(strava_creds and strava_creds.get("client_id"))

    with st.expander("⚙️ Configurer l'application Strava", expanded=not has_client):
        st.markdown(
            "Créez une application sur [strava.com/settings/api](https://www.strava.com/settings/api) "
            "et renseignez ci-dessous le **Client ID**, le **Client Secret** et l'**URL de redirection** "
            "configurée dans votre application Strava (doit correspondre exactement)."
        )
        with st.form("strava_config"):
            col_id, col_sec = st.columns(2)
            with col_id:
                client_id = st.text_input(
                    "Client ID",
                    value=strava_creds.get("client_id", "") if strava_creds else "",
                )
            with col_sec:
                client_secret = st.text_input(
                    "Client Secret",
                    type="password",
                    value=strava_creds.get("client_secret", "") if strava_creds else "",
                )
            redirect_uri = st.text_input(
                "URL de redirection",
                value=strava_creds.get("redirect_uri", "") if strava_creds else "",
                placeholder="https://votre-app.streamlit.app/sync",
                help="Doit être identique à l'URL déclarée dans votre application Strava.",
            )
            cfg_submitted = st.form_submit_button("💾 Enregistrer la configuration", use_container_width=True)

        if cfg_submitted:
            if not client_id or not client_secret or not redirect_uri:
                st.error("Client ID, Client Secret et URL de redirection sont tous requis.")
            else:
                save_strava_credentials({
                    "client_id": client_id.strip(),
                    "client_secret": client_secret.strip(),
                    "redirect_uri": redirect_uri.strip(),
                })
                st.success("✅ Configuration Strava enregistrée.")
                st.rerun()

    strava_creds = get_strava_credentials()
    if strava_creds and strava_creds.get("client_id") and strava_creds.get("redirect_uri"):
        auth_url = get_auth_url(strava_creds["client_id"], strava_creds["redirect_uri"])
        st.link_button("🔗 Connecter à Strava", auth_url, use_container_width=False)
        st.caption(
            "Vous serez redirigé vers Strava pour autoriser l'accès, "
            "puis renvoyé automatiquement sur cette page."
        )
