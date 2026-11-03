
    response.headers["Pragma"] = "no-cache"

    response.headers["Expires"] = "0"

    return response


# ==================================================
# PREVENT DASHBOARD CACHE
# ==================================================

@app.after_request
def prevent_cache(response):

    if request.endpoint in [
        "dashboard",
        "admin_login",
        "results",
        "create_job_route"
    ]:

        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate"
        )

        response.headers["Pragma"] = "no-cache"

        response.headers["Expires"] = "0"

    return response


# ==================================================
# COMPATIBILITY ENDPOINTS
# ==================================================

app.add_url_rule(
    "/results/<int:job_id>",
    endpoint="job_results",
    view_func=results
)

app.add_url_rule(
    "/delete-job/<int:job_id>",
    endpoint="delete_job_route",
    view_func=delete_job,
    methods=["POST"]
)

app.add_url_rule(
    "/create-job",
    endpoint="create_job_page",
    view_func=create_job_route,
    methods=["GET", "POST"]
)


# ==================================================
# ERROR HANDLERS
# ==================================================

@app.errorhandler(404)
def page_not_found(error):

    template_path = os.path.join(
        BASE_DIR,
        "templates",
        "404.html"
    )

    if os.path.isfile(template_path):

        return render_template("404.html"), 404

    return "Page not found.", 404


@app.errorhandler(413)
def file_too_large(error):

    return (
        "Resume file is too large. Maximum size is 16 MB.",
        413
    )


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=(
            os.environ.get(
                "FLASK_DEBUG",
                "false"
            ).lower() == "true"
        )
    )