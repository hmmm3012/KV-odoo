import base64
from io import BytesIO

from odoo import http
from odoo.http import content_disposition, request
from pdfrw import PageMerge, PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

department_decode = {
    "SAP": "SaiGon Airport",
    "Park IX": "Park IX",
    "DCH": "Deutsches Haus (Tòa nhà Đức)",
    "TĐP": "Thảo Điền Pearl",
    "DIL": "Diamond Islands (Đảo Kim Cương)",
    "SRCS": "Sunrise City South",
    "HLR": "HimLam Riverside",
    "HLPA": "Him Lam Phú An",
    "SWP": "Sunwan Pearl",
    "OPAL": "OPAL",
    "SGP": "Sài Gòn Pearl",
    "CM239": "Central Market ",
    "MTT": "Metropole Thủ Thiêm",
    "Sala-SRC": "Sala Sarica",
    "CVTT": "Công viên Thủ Thiêm",
    "TM-TC": "TTTM Thiso Mall Trường Chinh",
    "AEONBT": "TTTM AEON Mall Bình Tân",
    "AEONTP": "TTTM AEON Mall Tân Phú",
    "AEONBD": "TTTM AEON Mall Bình Dương",
    "AEONLB": "TTTM AEON Mall Long Biên",
    "AEONLC": "TTTM AEON Mall Hải Phòng",
    "ECO": "Chung cư Rừng Cọ",
    "Nghiệp vụ bãi xe": "Nghiệp vụ bãi xe",
    "PCM": "Parc Mall",
    "TOTT": "The Opera Thủ Thiêm",
    "Sala-SRM":"Sala Sarimi"
}


def add_overlay_to_pdf(input_pdf, overlay_pdf, output_pdf, page_number=0):
    # Read the existing PDF and the overlay PDF
    input_pdf_pages = PdfReader(input_pdf).pages
    overlay = PdfReader(overlay_pdf).pages[0]

    writer = PdfWriter(output_pdf)

    # Iterate through the input PDF pages and merge with the overlay
    # for page in input_pdf_pages:

    merger = PageMerge(input_pdf_pages[page_number])
    merger.add(overlay).render()
    writer.addpage(input_pdf_pages[page_number])

    writer.write()


def add_text_to_page(c, text, font, size, x, y, page_number):
    """
    Add text to a specified page of the PDF.

    Parameters:
    - c: The canvas instance.
    - text (str): The text to add.
    - font (str): The font name.
    - size (int): The font size.
    - x (int): The x-coordinate for the text's starting point.
    - y (int): The y-coordinate for the text's starting point.
    - page_number (int): The page number to add the text to.
    """
    c.setFont(font, size)
    page_height = A4[1]  # Get the height of the page
    c.drawString(
        x, page_height - (y), text
    )  # Adjust y-coordinate from the bottom of the page


def format_number_with_dots(number):
    # Convert the number to a string
    num_str = str(number)
    # Reverse the string to start grouping from the least significant digit
    reversed_num_str = num_str[-3::-1]
    # Insert a dot every three characters
    dotted_str = ".".join(
        reversed_num_str[i : i + 3] for i in range(0, len(reversed_num_str), 3)
    )
    # Reverse the string back to its original order
    formatted_str = dotted_str[::-1]
    return formatted_str


def search_and_replace_text(doc, original_text, new_text, font_name, font_size):
    for page in doc:
        text_instances = page.search_for(original_text)

        for inst in text_instances:
            text_x, text_y = inst[0], inst[1] + 12
            print(original_text, "x:", text_x, "y:", text_y)

    return doc


def create_pdf(contract):
    contract_name = contract.name
    employee_name = contract.employee_id.name
    date_start = contract.date_start
    date_end = contract.date_end
    job_id = contract.job_id.name
    temp_address = contract.employee_id.emp_temporary_address
    perm_address = contract.employee_id.emp_permanent_address
    employee_id = contract.employee_id.identification_id
    employee_id_date = contract.employee_id.identification_date
    employee_id_by = contract.employee_id.identification_by
    employee_birthday = contract.employee_id.birthday
    department = contract.employee_id.department_id.name
    salary = contract.wage
    # doc = fitz.open("dev/kv_hr_contract/report/pos_rp.pdf")
    # search_and_replace_text(doc, "%date_start%", employee_name, "tiro", 12)
    # search_and_replace_text(doc, "%date_end%", employee_name, "tiro", 12)
    # search_and_replace_text(doc, "%work_place%", employee_name, "tiro", 12)
    # search_and_replace_text(doc, "%%", employee_name, "tiro", 12)
    pdf_buffer1 = BytesIO()
    c1 = canvas.Canvas(pdf_buffer1, pagesize=A4)
    pdf_buffer2 = BytesIO()
    c2 = canvas.Canvas(pdf_buffer2, pagesize=A4)
    pdfmetrics.registerFont(
        TTFont(
            "tiro",
            r"D:\odoo16\utils\font\font-times-new-roman\SVN-TimesNewRoman.ttf",
        )
    )
    pdfmetrics.registerFont(
        TTFont(
            "tiro_bold",
            r"D:\odoo16\utils\font\font-times-new-roman\SVN-Times New Roman Bold.ttf",
        )
    )
    pdfmetrics.registerFont(
        TTFont(
            "tiro_italic",
            r"D:\odoo16\utils\font\font-times-new-roman\SVN-Times New Roman Italic.ttf",
        )
    )
    add_text_to_page(
        c1,
        contract_name,
        "tiro_bold",
        12,
        90.55000305175781,
        141.77198791503906 - 1,
        1,
    )
    add_text_to_page(
        c1,
        "Ngày "
        + str(date_start.day)
        + " tháng "
        + str(date_start.month)
        + " năm "
        + str(date_start.year),
        "tiro_italic",
        11,
        403.42999267578125,
        106.56903076171875 - 1.5,
        1,
    )
    add_text_to_page(
        c1,
        employee_name.upper(),
        "tiro_bold",
        12,
        193.8300018310547,
        295.94403076171875 - 1,
        1,
    )
    birthday = employee_birthday.strftime(("%d/%m/%Y"))
    add_text_to_page(
        c1,
        birthday,
        "tiro",
        12,
        180.5800018310547,
        311.2139892578125 - 1,
        1,
    )
    add_text_to_page(
        c1,
        perm_address,
        "tiro",
        12,
        172.5800018310547,
        326.4639892578125 - 1,
        1,
    )
    add_text_to_page(
        c1,
        temp_address,
        "tiro",
        12,
        151.8300018310547,
        341.7140197753906,
        1,
    )
    add_text_to_page(
        c1,
        employee_id,
        "tiro",
        12,
        128.3000030517578,
        356.9640197753906 - 1,
        1,
    )
    add_text_to_page(
        c1,
        employee_id_by,
        "tiro",
        12,
        265.6300048828125 + 4,
        356.9640197753906 - 1,
        1,
    )
    id_date = employee_id_date.strftime(("%d/%m/%Y"))
    add_text_to_page(
        c1,
        id_date,
        "tiro",
        12,
        407.92999267578125 + 5,
        356.9640197753906 - 1,
        1,
    )
    add_text_to_page(
        c1,
        format_number_with_dots(salary) + "đ/tháng.",
        "tiro",
        12,
        229.35000610351562 - 10,
        609.0440063476562 + 13,
        1,
    )
    add_text_to_page(
        c1,
        job_id,
        "tiro",
        12,
        160.0800018310547,
        460.9840087890625 + 13,
        1,
    )
    date_start = date_start.strftime(("%d/%m/%Y"))
    add_text_to_page(
        c2,
        "ngày " + date_start,
        "tiro_bold",
        12,
        191.3300018310547,
        459.90899658203125 - 1,
        1,
    )

    add_text_to_page(
        c1,
        date_start,
        "tiro",
        12,
        154.3300018310547,
        444.7340087890625 - 12,
        1,
    )
    add_text_to_page(
        c1,
        "Bãi xe " + department_decode[department],
        "tiro",
        12,
        218.85000610351562,
        458.7340087890625 - 12,
        1,
    )
    print(date_end)
    if date_end is not False:
        add_text_to_page(
            c1,
            date_end.strftime(("%d/%m/%Y")),
            "tiro",
            12,
            295.6300048828125,
            444.7340087890625 - 12,
            1,
        )
        period = contract.date_end.year - contract.date_start.year
        if period == 0:
            period = 1
        add_text_to_page(
            c1,
            str(period) + " năm.",
            "tiro",
            12,
            285.6300048828125,
            444.7340087890625 - 26,
            1,
        )
        add_text_to_page(
            c2,
            "30",
            "tiro",
            12,
            230.85000610351562 + 2,
            134.6639862060547 - 18,
            1,
        )
    else:
        add_text_to_page(
            c1,
            "không xác định.",
            "tiro",
            12,
            285.6300048828125,
            444.7340087890625 - 26,
            1,
        )
        add_text_to_page(
            c2,
            "45",
            "tiro",
            12,
            230.85000610351562 + 2,
            134.6639862060547 - 18,
            1,
        )

    # Save the PDF to the buffer
    c1.save()
    with open(r"D:\odoo16\dev\kv_hr_contract\report\overlay1.pdf", "wb") as pdf_file:
        pdf_file.write(pdf_buffer1.getvalue())
    # Save the PDF to the buffer
    c2.save()
    with open(r"D:\odoo16\dev\kv_hr_contract\report\overlay2.pdf", "wb") as pdf_file:
        pdf_file.write(pdf_buffer2.getvalue())

    add_overlay_to_pdf(
        r"D:\odoo16\dev\kv_hr_contract\report\rp_format.pdf",
        r"D:\odoo16\dev\kv_hr_contract\report\overlay1.pdf",
        r"D:\odoo16\dev\kv_hr_contract\report\output_page1.pdf",
        0,
    )
    add_overlay_to_pdf(
        r"D:\odoo16\dev\kv_hr_contract\report\rp_format.pdf",
        r"D:\odoo16\dev\kv_hr_contract\report\overlay2.pdf",
        r"D:\odoo16\dev\kv_hr_contract\report\output_page2.pdf",
        1,
    )
    pdf1_path = r"D:\odoo16\dev\kv_hr_contract\report\output_page1.pdf"
    pdf2_path = r"D:\odoo16\dev\kv_hr_contract\report\output_page2.pdf"
    writer = PdfWriter()

    # Read and add all pages from the first PDF
    for page in PdfReader(pdf1_path).pages:
        writer.addpage(page)

    # Read and add all pages from the second PDF
    for page in PdfReader(pdf2_path).pages:
        writer.addpage(page)

    # Write the combined pages to a new PDF file
    output_path = r"D:\odoo16\dev\kv_hr_contract\report\output.pdf"
    writer.write(output_path)
    with open(output_path, "rb") as pdf_file:
        pdf_buffer1 = pdf_file.read()
    return pdf_buffer1


class ContractPDFController(http.Controller):
    @http.route(["/contracts/pdf/<int:contract_id>"], type="http", auth="user")
    def download_pdf(self, contract_id, **kwargs):
        contract = request.env["hr.contract"].browse(contract_id)
        
        # Ensure the user has access to the contract
        if not contract.exists() or not request.env.user.has_group(
            "hr_contract.group_hr_contract_manager"
        ):
            return request.not_found()
        pdf_res = create_pdf(contract)

        headers = [
            ("Content-Type", "application/pdf"),
            (
                "Content-Disposition",
                content_disposition(f"{contract.name}.pdf"),
            ),
        ]
        return request.make_response(pdf_res, headers=headers)
