import requests
import re
from bs4 import BeautifulSoup, Tag

def check_has_diagram(content_div: Tag) -> bool:
    """Check if the problem section contains an image/diagram."""
    headers = content_div.find_all(["h2", "h3"])
    problem_header = None
    for h in headers:
        if re.match(r"^Problem(\s+\d+)?$", h.get_text(strip=True), re.IGNORECASE):
            problem_header = h
            break

    tags_to_check = [content_div] # Fallback
    if problem_header is not None:
        siblings = []
        for sibling in problem_header.find_next_siblings():
            if sibling.name in ("h2", "h3"):
                break
            siblings.append(sibling)
        if siblings:
            tags_to_check = siblings
            
    for tag in tags_to_check:
        if not isinstance(tag, Tag):
            continue
        imgs = [tag] if tag.name == "img" else tag.find_all("img")
        for img in imgs:
            alt = img.get("alt", "")
            src = img.get("src", "")
            classes = img.get("class", [])
            if isinstance(classes, str):
                classes = [classes]
                
            is_latex_class = any("latex" in c.lower() for c in classes)
            if "latex" not in src.lower() and not is_latex_class:
                if "AMC_Logo" not in src:
                    print(f"Diagram detected by non-latex: src={src}")
                    return True
            
            if "[asy]" in alt.lower() or "asymptote" in alt.lower():
                print(f"Diagram detected by [asy]: alt={alt[:30]}")
                return True
                
            if "latexcenter" in classes:
                width = img.get("width")
                if width and width.isdigit() and int(width) > 100:
                    print(f"Diagram detected by width: width={width}")
                    return True
                    
            # Fallback for size if it's a latex drawing but no class `latexcenter`
            width = img.get("width")
            height = img.get("height")
            if width and height and width.isdigit() and height.isdigit():
                if int(width) > 100 and int(height) > 100:
                    print(f"Diagram detected by w/h: {width}x{height}")
                    return True
                    
    return False

url = "https://artofproblemsolving.com/wiki/index.php/2023_AMC_10A_Problems/Problem_11"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.text, "html.parser")
content = soup.find("div", class_="mw-parser-output")

has_diag = check_has_diagram(content)
print(f"Result for P11: {has_diag}")

url_p2 = "https://artofproblemsolving.com/wiki/index.php/2023_AMC_10A_Problems/Problem_2"
resp_p2 = requests.get(url_p2, headers=headers)
soup_p2 = BeautifulSoup(resp_p2.text, "html.parser")
content_p2 = soup_p2.find("div", class_="mw-parser-output")

has_diag_p2 = check_has_diagram(content_p2)
print(f"Result for P2 (should be False): {has_diag_p2}")
