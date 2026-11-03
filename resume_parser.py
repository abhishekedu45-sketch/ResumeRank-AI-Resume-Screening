import os
import PyPDF2


# ============================================================
# EXTRACT TEXT FROM PDF RESUME
# ============================================================

def extract_text_from_pdf(pdf_path):

    text = ""

    try:

        # Check whether the PDF file exists
        if not os.path.exists(pdf_path):

            print("Resume PDF not found:", pdf_path)

            return ""

        # Check whether it is actually a file
        if not os.path.isfile(pdf_path):

            print("Invalid resume file path:", pdf_path)

            return ""

        # Open PDF file
        with open(pdf_path, "rb") as file:

            pdf_reader = PyPDF2.PdfReader(file)

            # Check whether PDF is encrypted
            if pdf_reader.is_encrypted:

                try:

                    decrypt_status = pdf_reader.decrypt("")

                    if not decrypt_status:

                        print("Unable to decrypt PDF")

                        return ""

                except Exception:

                    print("Unable to read encrypted PDF")

                    return ""

            # Check whether PDF contains pages
            if len(pdf_reader.pages) == 0:

                print("PDF contains no pages")

                return ""

            # Extract text from every page
            for page_number, page in enumerate(pdf_reader.pages):

                try:

                    page_text = page.extract_text()

                    if page_text:

                        text += page_text + "\n"

                except Exception as error:

                    print(
                        f"Error extracting page {page_number + 1}:",
                        error
                    )

                    continue

        # Return extracted text
        return text.strip()

    except Exception as error:

        print("Resume PDF extraction error:", error)

        return ""