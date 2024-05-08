from flask import Flask, request, render_template
from pypdf import PdfReader
import os
import re
import traceback
from openai import AzureOpenAI

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            resume_file = request.files.get('resume')
            job_desc_file = request.files.get('job_description')
            if not resume_file or not job_desc_file:
                return 'Missing files', 400
            
            if resume_file.filename == '' or job_desc_file.filename == '':
                return 'No selected file', 400

            if not resume_file.filename.endswith('.pdf') or not job_desc_file.filename.endswith('.pdf'):
                return 'Invalid file format, only PDFs are supported', 400

            temp_dir = 'temp'
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            # Process files
            resume_path = os.path.join(temp_dir, resume_file.filename)
            job_desc_path = os.path.join(temp_dir, job_desc_file.filename)
            resume_file.save(resume_path)
            job_desc_file.save(job_desc_path)

            resume_text, job_desc_text = extract_texts(resume_path, job_desc_path)
            if not resume_text or not job_desc_text:
                return "Failed to extract text from PDFs.", 500
            #api_key = os.getenv('AZURE_OPENAI_API_KEY')
            client = AzureOpenAI(
                azure_endpoint="https://uploadtesting-0504.openai.azure.com/", 
                api_key="e3c5768d3dd347029304eed9f1cecd9e",  
                api_version="2024-02-15-preview"
            )
            jdshort, score, reasoning = analyze_documents(client, job_desc_text, resume_text)
            return render_template('display.html', score=score, reasoning="REASONING - " + reasoning)
        
        except Exception as e:
            traceback.print_exc()
            return f"An error occurred: {str(e)}", 500

    return render_template('upload.html')

def extract_texts(resume_path, job_desc_path):
    resume_text = ''
    job_desc_text = ''
    resume_reader = None
    job_desc_reader = None
    try:
        resume_reader = PdfReader(resume_path)
        for page in resume_reader.pages:
            text = page.extract_text()
            if text:
                resume_text += text

        job_desc_reader = PdfReader(job_desc_path)
        for page in job_desc_reader.pages:
            text = page.extract_text()
            if text:
                job_desc_text += text
    except Exception as e:
        traceback.print_exc()
        print(f"Failed to read PDF files: {str(e)}")
    finally:
        os.remove(resume_path)
        os.remove(job_desc_path)
    return resume_text, job_desc_text

def analyze_documents(client, job_desc_text, resume_text):
    try:
        # Shorten job description
        jd_prompt = ("Shorten the attached job description by getting rid of all repetitive technologies, remove all benefits "
                     "and remove the interview process, only keeping all the job requirements in place - " + job_desc_text)
        jd_message = [{"role": "system", "content": jd_prompt}]
        jd_completion = client.chat.completions.create(
            model="chat_testing", # Replace with actual model identifier
            messages=jd_message,
            temperature=0.7,
            max_tokens=800,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )
        jdshort = jd_completion.choices[0].message.content

        # Analyze resume match
        analysis_prompt = ('''I will attach a resume converted to text below and then add a job description further below. You are a hiring team consisting of engineers, HR, managers, and high-level executives who judge resumes for the attached job descriptions. You will output 2 things. First should be a fair but strict and unbiased score from 0-10 indicating how well the applicant's resume matches the job description, specifically, their education, their internship and research experiences, their project work, their leadership, and soft skills. Focus especially on the quantitative and qualitative upgrades they added in their experience, and also focus very specifically on the technologies they used, what are the most important and overlapping skills from the applicant's resume with the job description, and what are the skills required in the JD not present in the resume. Also, focus on the branch of study the student does, and then if the school they went to is known for that particular field of study, how relevant it is to the requirements as laid out in the job description., and if they should be further interviewed for this role or not. You should analyze all parts of the resume and the job description and make sure that you understand that your score and analysis might cost your company millions of dollars since this is a very high-value job and candidate. Next output should be a 3-4 line (100 words) sharing critical details and skills that overlap and those that are missing So analyze this extremely carefully without overlooking any gaps or details. Make sure you only output these 2 things - first line should be "Score - X/10" and second line - "Reasoning - " and then a 2-4 line (maximum 100 word strict limit) reasoning. Make sure you stick to this output format and word limit extremely strictly, do not output any reasoning more than 100 words, highlighting only the important parts.''' +
                        "\nResume - " + resume_text + "\nJob Description - \n" + jdshort)
        analysis_message = [{"role": "system", "content": analysis_prompt}]
        analysis_completion = client.chat.completions.create(
            model="chat_testing", # Replace with actual model identifier
            messages=analysis_message,
            temperature=0.7,
            max_tokens=800,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )
        analysis_response = analysis_completion.choices[0].message.content

        # Extract score and reasoning using regex
        score_match = re.search(r'Score - (\d+/10)', analysis_response)
        reasoning_match = re.search(r'Reasoning - (.*)', analysis_response, re.DOTALL)
        
        if score_match and reasoning_match:
            score = score_match.group(1)
            reasoning = reasoning_match.group(1)
        else:
            score = "No score available"
            reasoning = "No detailed reasoning provided."
        
        return jdshort, score, reasoning
    except Exception as e:
        traceback.print_exc()
        return "", "API call failed", "Unable to analyze documents due to an internal error."

if __name__ == '__main__':
    app.run(debug=False)
