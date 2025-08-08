from streamlit.web import bootstrap

def main():
    bootstrap.run('streamlit_app.py', '', [], flag_options={})

if __name__ == '__main__':
    main()
