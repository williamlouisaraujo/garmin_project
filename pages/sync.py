import streamlit as st

from src.garmin_client import fetch_activities, fetch_all_activities
from src.storage import (
    delete_strava_account,
    get_accounts,
    get_last_sync,
    get_strava_account_for_garmin,
    get_strava_accounts,
    get_strava_app_config,
    save_accounts,
    save_activities,
    save_strava_app_config,
)
from src.strava_client import get_auth_url
from src.strava_sync import run_strava_sync

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

# ═════════════════════════════════════════════════════════════════════════════
# STRAVA
# ═════════════════════════════════════════════════════════════════════════════
st.subheader("Strava")
st.caption(
    "Un seul compte développeur Strava suffit pour tous les utilisateurs. "
    "Chaque utilisateur se connecte ensuite individuellement via OAuth."
)

# ── Résultat de la connexion OAuth (traité dans app.py, affiché ici) ──────────
if st.session_state.get("_strava_connect_success"):
    _email = st.session_state.pop("_strava_connect_success")
    _name = st.session_state.pop("_strava_connect_athlete", _email)
    st.success(f"✅ Strava connecté pour **{_name}** ({_email}).")
elif st.session_state.get("_strava_connect_error"):
    _err = st.session_state.pop("_strava_connect_error")
    st.error(f"❌ Erreur OAuth Strava : {_err}")
    st.info("Vérifiez que le Client Secret est correct et que le code n'a pas expiré (valable 10 min).")

# ── Configuration de l'application Strava (partagée) ─────────────────────────
app_cfg = get_strava_app_config()
has_app_cfg = bool(app_cfg and app_cfg.get("client_id") and app_cfg.get("client_secret"))

with st.expander(
    "⚙️ Application Strava (configuration partagée)",
    expanded=not has_app_cfg,
):
    st.markdown(
        "Créez une application sur [strava.com/settings/api](https://www.strava.com/settings/api). "
        "Cette configuration est partagée par tous les utilisateurs de l'app.\n\n"
        "**Domaine du rappel pour l'autorisation** (dans Strava) : uniquement le domaine, "
        "sans `https://` ni chemin. Ex : `garmin-project-app-wa.streamlit.app`"
    )
    with st.form("strava_app_config"):
        col_id, col_sec = st.columns(2)
        with col_id:
            _cid = st.text_input(
                "Client ID",
                value=app_cfg.get("client_id", "") if app_cfg else "",
            )
        with col_sec:
            _csec = st.text_input(
                "Client Secret",
                type="password",
                value=app_cfg.get("client_secret", "") if app_cfg else "",
            )
        _ruri = st.text_input(
            "URL de redirection",
            value=app_cfg.get("redirect_uri", "") if app_cfg else "",
            placeholder="https://garmin-project-app-wa.streamlit.app/sync",
            help="URL complète de cette page — doit correspondre exactement à ce qui est déclaré dans Strava.",
        )
        _cfg_ok = st.form_submit_button("💾 Enregistrer la configuration", use_container_width=True)

    if _cfg_ok:
        if not _cid or not _csec or not _ruri:
            st.error("Les trois champs sont requis.")
        else:
            save_strava_app_config({
                "client_id": _cid.strip(),
                "client_secret": _csec.strip(),
                "redirect_uri": _ruri.strip(),
            })
            st.success("✅ Configuration Strava enregistrée.")
            st.rerun()

# ── Connexion Strava par compte Garmin ────────────────────────────────────────
app_cfg = get_strava_app_config()

if not accounts:
    st.info("ℹ️ Ajoutez d'abord un compte Garmin pour pouvoir lier Strava.")
elif not has_app_cfg:
    st.info("ℹ️ Configurez l'application Strava ci-dessus avant de connecter les comptes.")
else:
    st.markdown("**Connexion Strava par utilisateur**")
    st.caption(
        "Chaque utilisateur autorise l'accès à son propre compte Strava. "
        "Le bouton ouvre une page Strava dans un nouvel onglet — après autorisation, "
        "vous serez redirigé automatiquement ici."
    )

    for account in accounts:
        garmin_email = account["email"]
        garmin_label = account.get("label") or garmin_email
        strava_acc = get_strava_account_for_garmin(garmin_email)
        is_linked = bool(strava_acc and strava_acc.get("access_token"))

        with st.container(border=True):
            col_info, col_action, col_del = st.columns([4, 3, 1])

            with col_info:
                st.markdown(f"**{garmin_label}**")
                if is_linked:
                    athlete = strava_acc.get("athlete") or {}
                    athlete_name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
                    st.caption(f"Strava : {athlete_name or 'connecté'} ✅")
                else:
                    st.caption("Strava : non connecté")

            with col_action:
                if is_linked:
                    if st.button("🔄 Sync Strava", key=f"strava_sync_{garmin_email}", use_container_width=True):
                        with st.spinner("Synchronisation Strava en cours…"):
                            try:
                                sync_res = run_strava_sync(app_cfg, strava_acc)
                                st.success(
                                    f"✅ Sync {sync_res.mode} terminée — activités: {sync_res.fetched_activities} (upserts {sync_res.upserted_activities}), "
                                    f"détails: {sync_res.detailed_activities}, best_efforts: {sync_res.upserted_best_efforts}, appels API: {sync_res.api_calls}."
                                )
                                st.caption(
                                    f"Fenêtre chargée: min={sync_res.oldest_activity_date_loaded}, max={sync_res.latest_activity_date_loaded}, "
                                    f"backfill_completed={sync_res.backfill_completed}"
                                )
                                if sync_res.rate_limit_limit and sync_res.rate_limit_usage:
                                    st.caption(
                                        f"Rate limit Strava (15min, jour): usage={sync_res.rate_limit_usage} / limite={sync_res.rate_limit_limit}"
                                    )
                            except ValueError as exc:
                                st.error(f"⚠️ {exc}")
                            except RuntimeError as exc:
                                st.error(f"⏱️ {exc}")
                            except Exception as exc:
                                st.error(f"❌ Erreur Strava : {exc}")
                else:
                    auth_url = get_auth_url(
                        app_cfg["client_id"],
                        app_cfg["redirect_uri"],
                        state=garmin_email,
                    )
                    st.link_button(
                        "🔗 Connecter Strava",
                        auth_url,
                        use_container_width=True,
                    )

            with col_del:
                if is_linked:
                    if st.button("🗑️", key=f"strava_del_{garmin_email}", help="Déconnecter Strava"):
                        delete_strava_account(garmin_email)
                        st.rerun()

# ── Debug Strava ──────────────────────────────────────────────────────────────
with st.expander("🔍 Debug Strava", expanded=False):
    st.write("**Paramètres URL détectés :**", dict(st.query_params) or "_aucun_")
    _dbg_cfg = get_strava_app_config()
    st.write("**App config :**", {
        "client_id": _dbg_cfg.get("client_id", "—") if _dbg_cfg else "—",
        "client_secret": "***" if (_dbg_cfg and _dbg_cfg.get("client_secret")) else "—",
        "redirect_uri": _dbg_cfg.get("redirect_uri", "—") if _dbg_cfg else "—",
    })
    _dbg_strava_accounts = get_strava_accounts()
    st.write(f"**Comptes Strava liés ({len(_dbg_strava_accounts)}) :**")
    for _sa in _dbg_strava_accounts:
        _ath = _sa.get("athlete") or {}
        st.write({
            "garmin_email": _sa.get("garmin_email"),
            "athlete": f"{_ath.get('firstname', '')} {_ath.get('lastname', '')}".strip() or "—",
            "access_token": "présent ✅" if _sa.get("access_token") else "absent ❌",
        })
    if not _dbg_strava_accounts:
        st.write("_aucun_")
