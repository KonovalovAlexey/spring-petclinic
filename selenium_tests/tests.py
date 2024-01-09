# Selenium test examples
import time
from mimetypes import guess_type
import pytest
from selenium import webdriver
from selenium.webdriver import DesiredCapabilities
from selenium.webdriver.common.by import By
from reportportal_client import RPLogger
import logging
import os

link = os.environ.get('APP_TARGET_URL')
selenium_server_url = os.environ.get('SELENIUM_SERVER_URL')


@pytest.fixture(scope="session")
def rp_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logging.setLoggerClass(RPLogger)
    return logger


@pytest.fixture(scope="session")
def browser():
    print("\nstart browser for test..")
    browser = webdriver.Remote(
        command_executor=selenium_server_url,
        desired_capabilities=DesiredCapabilities.FIREFOX
    )
    # browser = webdriver.Chrome()
    yield browser
    print("\nquit browser..")
    browser.quit()


class TestApp:

    # Test for failing testing, uncomment it if need one test will be failed
    # def test_fail(self):
    #     assert (1 == 2)

    def test_success(self):
        print('Pass test 2 = 2 success')
        assert (2 == 2)

    def test_open_title(self, browser, rp_logger):
        browser.get(link)
        browser.save_screenshot("ss.png")
        image = "./ss.png"
        with open(image, "rb") as image_file:
            rp_logger.info("ScreenShot Title Page",
                           attachment={"name": "ss.png",
                                       "data": image_file.read(),
                                       "mime": guess_type(image)[0] or "application/octet-stream"},
                           )
        print("Title is : " + browser.title)

    def test_title(self, browser):
        assert ("PetClinic" in browser.title)

    def test_welcome_page(self, browser):
        browser.find_element(by=By.XPATH, value='//*[@id="main-navbar"]/ul/li[2]/a').click()
        assert ("Find Owners" == browser.find_element(by=By.XPATH, value="/html/body/div/div/h2").text)

    def test_oups_page(self, browser):
        browser.find_element(by=By.XPATH, value='//*[@id="main-navbar"]/ul/li[4]/a/span[2]').click()
        assert ("Something happened..." == browser.find_element(by=By.XPATH, value="/html/body/div/div/h2").text)