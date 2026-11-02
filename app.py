import os
import re

import uuid



from flask import (

    Flask,

    render_template,

    request,

    redirect,

    url_for,

    session,

    flash

)



from flask_mail import Mail, Message

from werkzeug.utils import secure_filename

from dotenv import load_dotenv

from PyPDF2 import PdfReader



from database import (

    initialize_database,

    create_job,

    get_all_jobs,

    get_job,

    get_job_by_link,

    get_candidate_count,

    get_total_candidates,

    create_candidate,

    get_candidates_by_job,

    save_result,

    get_job_results,

    get_high_match_count,

    delete_job

)





# ============================================================

# LOAD ENVIRONMENT VARIABLES

# ============================================================



load_dotenv()





# ============================================================

# FLASK APP

# ============================================================



app = Flask(__name__)

